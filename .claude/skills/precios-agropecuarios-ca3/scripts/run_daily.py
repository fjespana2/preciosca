"""
Orquestador de la recolección diaria.

FASE 1  ->  python run_daily.py fetch
    - Guatemala: descarga + parsea el HTML            -> staging/gt.json   (LISTO)
    - Honduras:  descarga + parsea el PDF             -> staging/hn.json   (LISTO)
    - Nicaragua: descarga las 5 imágenes PNG          -> staging/ni_PLANTILLA.json
                 (NO se puede parsear con código: Claude debe transcribirlas)

    >>> Aquí Claude abre cada imagen de 'imagenes/', transcribe las filas y
    >>> guarda staging/ni.json (misma estructura que la plantilla).

FASE 2  ->  python run_daily.py ingest
    - Normaliza staging/ni.json                       -> staging/ni_registros.json
    - Trae el tipo de cambio USD del día
    - Inserta/actualiza los 3 países en SQLite (sin duplicar)
    - Regenera los CSV de export/
    - Escribe logs/run_AAAA-MM-DD.json y lo imprime

`python run_daily.py all` intenta las dos fases seguidas: sólo funciona si
staging/ni.json ya existe (p.ej. en una segunda corrida del mismo día).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

HERE = Path(__file__).parent
PY = sys.executable


def _run(script: str, *cli: str) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, str(HERE / script), *cli],
        capture_output=True, text=True,
    )
    salida = (proc.stdout or "") + (proc.stderr or "")
    print(salida.rstrip())
    return proc.returncode, salida


def _asegura_dependencias() -> None:
    """Instala pdfplumber/requests/bs4/lxml si faltan (Honduras no corre sin pdfplumber)."""
    import importlib.util as u
    faltan = [m for m, pip in (
        ("pdfplumber", "pdfplumber"), ("requests", "requests"),
        ("bs4", "beautifulsoup4"), ("lxml", "lxml"),
    ) if u.find_spec(m) is None]
    if faltan:
        print(f"[run] instalando dependencias: {faltan}")
        subprocess.run([PY, "-m", "pip", "install", "--quiet", *[
            {"bs4": "beautifulsoup4"}.get(m, m) for m in faltan]], check=False)


def fase_fetch() -> dict:
    carpeta = common.carpeta_datos()
    _asegura_dependencias()
    estado = {"fase": "fetch", "cuando": datetime.now().isoformat(timespec="seconds"),
              "pasos": {}}

    rc_gt, _ = _run("extract_guatemala.py")
    estado["pasos"]["guatemala"] = "ok" if rc_gt == 0 else "ERROR"

    rc_hn, _ = _run("extract_honduras.py")
    estado["pasos"]["honduras"] = "ok" if rc_hn == 0 else "ERROR"

    rc_ni, _ = _run("nicaragua_fetch.py")
    estado["pasos"]["nicaragua_imagenes"] = "ok" if rc_ni == 0 else "ERROR"

    plantilla = carpeta / "staging" / "ni_PLANTILLA.json"
    estado["nicaragua_plantilla"] = str(plantilla)
    estado["siguiente"] = (
        "Claude: transcribe las imágenes listadas en la plantilla y guarda "
        f"{carpeta / 'staging' / 'ni.json'}; luego corre: python run_daily.py ingest"
    )
    (carpeta / "logs" / "_ultimo_fetch.json").write_text(
        json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + estado["siguiente"])
    return estado


def fase_ingest() -> dict:
    carpeta = common.carpeta_datos()
    staging = carpeta / "staging"
    estado = {"fase": "ingest", "cuando": datetime.now().isoformat(timespec="seconds"),
              "pasos": {}}

    if not (staging / "ni.json").exists():
        print(f"[run] FALTA {staging / 'ni.json'} — Claude debe transcribir las "
              f"imágenes primero (ver staging/ni_PLANTILLA.json).", file=sys.stderr)
        return {"error": "falta staging/ni.json"}

    rc_ni, _ = _run("nicaragua_ingest.py")
    estado["pasos"]["nicaragua_normaliza"] = "ok" if rc_ni == 0 else "ERROR"

    # tasa de respaldo de Honduras (del PDF) para fx si la API falla
    tc_hnl = None
    hn_json = staging / "hn.json"
    if hn_json.exists():
        tc_hnl = json.loads(hn_json.read_text(encoding="utf-8")).get("tc_usd_hnl_pdf")

    fuentes = [staging / "gt.json", staging / "hn.json", staging / "ni_registros.json"]
    fuentes = [f for f in fuentes if f.exists()]
    cli = ["ingest", "--registros", *map(str, fuentes)]
    if tc_hnl:
        cli += ["--tc-hnl-respaldo", str(tc_hnl)]
    rc_db, out_db = _run("db.py", *cli)
    estado["pasos"]["db_ingest"] = "ok" if rc_db == 0 else "ERROR"
    try:
        estado["ingest"] = json.loads(out_db[out_db.index("{"):])
    except (ValueError, json.JSONDecodeError):
        estado["ingest"] = {"crudo": out_db}

    rc_ex, out_ex = _run("db.py", "export")
    estado["pasos"]["export"] = "ok" if rc_ex == 0 else "ERROR"

    rc_rs, out_rs = _run("db.py", "resumen")
    try:
        estado["resumen_db"] = json.loads(out_rs[out_rs.index("{"):])
    except (ValueError, json.JSONDecodeError):
        pass

    # log con timestamp (no se pisa entre corridas del mismo día) + historial acumulativo
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log = carpeta / "logs" / f"run_{ts}.json"
    log.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    with (carpeta / "logs" / "historial.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(estado, ensure_ascii=False) + "\n")
    print(f"\n[run] log -> {log}")
    print("[run] historial acumulativo -> logs/historial.jsonl y tabla `corridas`")
    return estado


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fase", choices=["fetch", "ingest", "all"])
    args = ap.parse_args()

    if args.fase == "fetch":
        fase_fetch()
    elif args.fase == "ingest":
        r = fase_ingest()
        if r.get("error"):
            return 1
    else:
        fase_fetch()
        print("\n--- intentando ingest (requiere staging/ni.json) ---")
        fase_ingest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
