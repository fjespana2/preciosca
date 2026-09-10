"""
Base de datos SQLite acumulada + exports CSV.

Tablas:
  registros  -> un renglón por (fecha, país, mercado, producto, tamaño, unidad).
                'hash' es UNIQUE: correr dos veces el mismo día ACTUALIZA, no duplica.
  corridas   -> bitácora: qué se ingirió cada día, tasas usadas, errores.

Archivos (en la carpeta de datos, por defecto ~/precios-agropecuarios-ca3):
  precios_ca3.sqlite
  export/precios_ca3.csv                (todo el histórico, formato largo/tidy)
  export/precios_guatemala.csv
  export/precios_honduras.csv
  export/precios_nicaragua.csv

Uso directo:
  python db.py init
  python db.py ingest --registros staging/gt.json staging/hn.json staging/ni_registros.json
  python db.py export
  python db.py resumen
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402
import fx as fx_mod  # noqa: E402

DB_NAME = "precios_ca3.sqlite"

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS registros (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    {", ".join(f"{c} TEXT" for c in common.COLUMNAS if c not in (
        "precio_min","precio_max","precio_moda","precio_prom","precio_ref",
        "precio_lb_local","cantidad_lb","tc_usd","precio_ref_usd","precio_lb_usd"))},
    precio_min      REAL, precio_max REAL, precio_moda REAL, precio_prom REAL,
    precio_ref      REAL, precio_lb_local REAL, cantidad_lb REAL,
    tc_usd          REAL, precio_ref_usd REAL, precio_lb_usd REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_registros_hash ON registros(hash);
CREATE INDEX IF NOT EXISTS ix_registros_fecha ON registros(fecha);
CREATE INDEX IF NOT EXISTS ix_registros_pais_fecha ON registros(pais, fecha);
CREATE INDEX IF NOT EXISTS ix_registros_prodnorm ON registros(producto_norm);

CREATE TABLE IF NOT EXISTS corridas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_reporte TEXT,
    ejecutado_en  TEXT,
    gt_filas      INTEGER, hn_filas INTEGER, ni_filas INTEGER,
    filas_nuevas  INTEGER, filas_actualizadas INTEGER,
    tc_gtq REAL, tc_hnl REAL, tc_nio REAL, tc_fallback INTEGER,
    errores       TEXT, notas TEXT
);
"""

_NUM = {"precio_min", "precio_max", "precio_moda", "precio_prom", "precio_ref",
        "precio_lb_local", "cantidad_lb", "tc_usd", "precio_ref_usd", "precio_lb_usd"}
_COLS = [c for c in common.COLUMNAS] + [
    "precio_ref_usd", "precio_lb_usd", "tc_usd",
]
# quitar duplicados preservando orden
_COLS = list(dict.fromkeys(_COLS))


def ruta_db() -> Path:
    return common.carpeta_datos() / DB_NAME


def conecta() -> sqlite3.Connection:
    con = sqlite3.connect(ruta_db())
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def _enriquece_usd(r: dict, tasas: dict) -> dict:
    tc = tasas.get(r.get("moneda"))
    r["tc_usd"] = tc
    if tc and r.get("precio_ref") is not None:
        r["precio_ref_usd"] = round(r["precio_ref"] / tc, 4)
    if tc and r.get("precio_lb_local") is not None:
        r["precio_lb_usd"] = round(r["precio_lb_local"] / tc, 6)
    return r


def ingest(paths: list[Path], tc_hnl_respaldo: float | None = None) -> dict:
    con = conecta()
    cur = con.cursor()

    tc = fx_mod.obtiene_tc(tc_hnl_respaldo)
    tasas = tc["tasas"]

    PAISES = ("Guatemala", "Honduras", "Nicaragua")
    por_pais = {p: 0 for p in PAISES}
    nuevas = {p: 0 for p in PAISES}
    actualizadas = {p: 0 for p in PAISES}
    errores: list[str] = []
    fechas_por_fuente: dict[str, str] = {}

    for path in paths:
        if not Path(path).exists():
            errores.append(f"no existe: {path}")
            continue
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        registros = data.get("registros", [])
        if data.get("pais") and data.get("fecha"):
            fechas_por_fuente[data["pais"]] = data["fecha"]

        for raw in registros:
            # los json de GT/HN ya vienen como registro canónico; NI también (tras ingest)
            r = {c: raw.get(c) for c in common.COLUMNAS}
            if not r.get("hash"):
                r = common.construye_registro(**raw)
            problemas = common.valida_registro(r)
            if problemas:
                errores.append(f"{r.get('pais')}/{r.get('producto')}: {'; '.join(problemas)}")
                continue
            _enriquece_usd(r, tasas)
            pais = r.get("pais")
            if pais in por_pais:
                por_pais[pais] += 1

            ya_existe = cur.execute(
                "SELECT 1 FROM registros WHERE hash=?", (r["hash"],)
            ).fetchone() is not None

            cols = [c for c in _COLS]
            vals = [r.get(c) for c in cols]
            marc = ",".join("?" * len(cols))
            setexpr = ",".join(f"{c}=excluded.{c}" for c in cols if c != "hash")
            cur.execute(
                f"INSERT INTO registros ({','.join(cols)}) VALUES ({marc}) "
                f"ON CONFLICT(hash) DO UPDATE SET {setexpr}",
                vals,
            )
            if pais in por_pais:
                (actualizadas if ya_existe else nuevas)[pais] += 1
        con.commit()

    tot_nuevas = sum(nuevas.values())
    tot_act = sum(actualizadas.values())
    notas = "; ".join(
        f"{p}: {fechas_por_fuente.get(p, 's/f')} ({nuevas[p]} nuevas, {actualizadas[p]} act)"
        for p in PAISES
    )

    cur.execute(
        "INSERT INTO corridas (fecha_reporte, ejecutado_en, gt_filas, hn_filas, ni_filas, "
        "filas_nuevas, filas_actualizadas, tc_gtq, tc_hnl, tc_nio, tc_fallback, errores, notas) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (datetime.now().date().isoformat(), datetime.now().isoformat(timespec="seconds"),
         por_pais["Guatemala"], por_pais["Honduras"], por_pais["Nicaragua"],
         tot_nuevas, tot_act,
         tasas["GTQ"], tasas["HNL"], tasas["NIO"], int(tc["es_fallback"]),
         " | ".join(errores[:50]) or None, notas),
    )
    con.commit()

    total = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
    con.close()
    return {
        "fecha_corrida": datetime.now().date().isoformat(),
        "fechas_por_fuente": fechas_por_fuente, "por_pais": por_pais,
        "filas_nuevas_por_pais": nuevas, "filas_actualizadas_por_pais": actualizadas,
        "filas_nuevas": tot_nuevas, "filas_actualizadas": tot_act, "total_db": total,
        "tc": tasas, "tc_fallback": tc["es_fallback"], "errores": errores,
    }


def export() -> dict:
    con = conecta()
    carpeta = common.carpeta_datos() / "export"
    cols = [c for c in _COLS if c != "hash"] + ["hash"]

    def _dump(nombre: str, where: str = "", params: tuple = ()):
        rows = con.execute(
            f"SELECT {','.join(cols)} FROM registros {where} ORDER BY fecha, pais, categoria, producto",
            params,
        ).fetchall()
        p = carpeta / nombre
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for row in rows:
                w.writerow([row[c] for c in cols])
        return len(rows)

    n_all = _dump("precios_ca3.csv")
    n_gt = _dump("precios_guatemala.csv", "WHERE pais=?", ("Guatemala",))
    n_hn = _dump("precios_honduras.csv", "WHERE pais=?", ("Honduras",))
    n_ni = _dump("precios_nicaragua.csv", "WHERE pais=?", ("Nicaragua",))
    con.close()
    return {"ca3": n_all, "guatemala": n_gt, "honduras": n_hn, "nicaragua": n_ni}


def resumen() -> dict:
    con = conecta()
    r = {
        "total": con.execute("SELECT COUNT(*) FROM registros").fetchone()[0],
        "por_pais": {row["pais"]: row["n"] for row in con.execute(
            "SELECT pais, COUNT(*) n FROM registros GROUP BY pais")},
        "rango_fechas": list(con.execute(
            "SELECT MIN(fecha), MAX(fecha) FROM registros").fetchone()),
        "dias_distintos": con.execute(
            "SELECT COUNT(DISTINCT fecha) FROM registros").fetchone()[0],
        "ultimas_corridas": [dict(row) for row in con.execute(
            "SELECT fecha_reporte, ejecutado_en, gt_filas, hn_filas, ni_filas, "
            "tc_fallback FROM corridas ORDER BY id DESC LIMIT 5")],
    }
    con.close()
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    pi = sub.add_parser("ingest")
    pi.add_argument("--registros", nargs="+", required=True)
    pi.add_argument("--tc-hnl-respaldo", type=float, default=None)
    sub.add_parser("export")
    sub.add_parser("resumen")
    args = ap.parse_args()

    if args.cmd == "init":
        conecta().close()
        print(f"[DB] lista -> {ruta_db()}")
    elif args.cmd == "ingest":
        res = ingest([Path(p) for p in args.registros], args.tc_hnl_respaldo)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "export":
        print(json.dumps(export(), ensure_ascii=False, indent=2))
    elif args.cmd == "resumen":
        print(json.dumps(resumen(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
