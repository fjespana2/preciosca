"""
Honduras — SIMPAH (SAG), reportes diarios de precios.

FUENTE ACTUAL (desde sep-2026): la SAG publica los PDF en su WordPress
  Página:  https://sag.gob.hn/secciones/publicaciones/simpah/
  Listado: https://sag.gob.hn/wp-json/wp/v2/media?mime_type=application/pdf&after=...
  Nombre:  <MERCADO>_<TIPO>_<AAAAMMDD>[-_]<No>.pdf
           MERCADO: SPSCA (Central de Abastos de Sula), SPSMC (Medina-Concepción, SPS),
                    TGAZB (Zonal Belén, Tegucigalpa)
           TIPO:    HOR (hortalizas), FRU (frutas), GB (granos básicos mayorista),
                    GBMN (granos básicos minorista)

La fuente anterior (fhia.org.hn, 2.1._reporte_diario_...pdf) dejó de actualizarse el
24-ago-2026; ya no se usa.

Cada corrida baja TODOS los reportes publicados desde la última fecha de Honduras en
la base (máx. 60 días atrás), así se recuperan solos los días que falten.

Los PDF son de texto nativo. Columnas:
  HOR/FRU: Producto | Origen | Tamaño | Unidad | Rango bajo | Rango alto | Moda bajo | Moda alto
  GB/GBMN: Producto | Origen | Unidad | Rango bajo | Rango alto | Moda bajo | Moda alto
Cuando el precio no tiene rango, el PDF trae solo 2 números (precio único).

Uso:
  python extract_honduras.py                   # descarga lo nuevo -> staging/hn.json
  python extract_honduras.py --desde 2026-10-01
  python extract_honduras.py --pdf a.pdf b.pdf # PDFs locales (pruebas)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

PAGINA = "https://sag.gob.hn/secciones/publicaciones/simpah/"
API = "https://sag.gob.hn/wp-json/wp/v2/media"
PAIS = "Honduras"
FUENTE = "SIMPAH (SAG)"
MONEDA = "HNL"
UA = {"User-Agent": "Mozilla/5.0 (precios-ca3/2.0)"}

TIPOS = {  # tipo -> (pista categoría, segmento, trae columna tamaño)
    "HOR": ("hortalizas", "mayorista", True),
    "FRU": ("frutas", "mayorista", True),
    "GB": ("granos basicos", "mayorista", False),
    "GBMN": ("granos basicos", "minorista", False),
}
MERCADOS = {
    "SPSCA": ("Mercado Central de Abastos de Sula", "San Pedro Sula"),
    "SPSMC": ("Mercado Medina-Concepción", "San Pedro Sula"),
    "TGAZB": ("Mercado Zonal Belén", "Tegucigalpa"),
}
_PATRON = re.compile(r"/([A-Z]+)_([A-Z]+)_(\d{8})[-_]?(\d+)?\.pdf$", re.I)


# ---------------------------------------------------------------- descarga
def _ultima_fecha_db() -> date | None:
    db = common.carpeta_datos() / "precios_ca3.sqlite"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(db)
        f = con.execute("SELECT MAX(fecha) FROM registros WHERE pais=?", (PAIS,)).fetchone()[0]
        return date.fromisoformat(f) if f else None
    except sqlite3.Error:
        return None


def lista_reportes(desde: date) -> list[dict]:
    """Reportes SIMPAH publicados desde `desde` (fecha del reporte, no de subida)."""
    out, pagina = {}, 1
    after = (desde - timedelta(days=3)).isoformat() + "T00:00:00"
    while True:
        r = requests.get(API, timeout=60, headers=UA, params={
            "mime_type": "application/pdf", "after": after, "per_page": 100,
            "page": pagina, "_fields": "source_url"})
        if r.status_code == 400:  # página fuera de rango
            break
        r.raise_for_status()
        items = r.json()
        for it in items:
            url = it["source_url"]
            m = _PATRON.search(url)
            if not m:
                continue
            merc, tipo, ymd, _ = m.groups()
            merc, tipo = merc.upper(), tipo.upper()
            if tipo not in TIPOS or merc not in MERCADOS:
                continue
            f = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:]))
            if f >= desde:
                out[(merc, tipo, f)] = {"url": url, "mercado": merc, "tipo": tipo, "fecha": f}
        if len(items) < 100:
            break
        pagina += 1
    return sorted(out.values(), key=lambda x: (x["fecha"], x["mercado"], x["tipo"]))


def descarga(url: str, destino: Path) -> Path:
    r = requests.get(url, timeout=90, headers=UA)
    r.raise_for_status()
    destino.write_bytes(r.content)
    return destino


# ---------------------------------------------------------------- parseo
def _meta(texto: str, nombre: str) -> dict:
    m = _PATRON.search("/" + nombre)
    merc = m.group(1).upper() if m else None
    tipo = m.group(2).upper() if m else None
    rid = None
    mm = re.search(r"C[oó]digo reporte:\s*([A-Z_]+),?\s*No\.?\s*(\d+)", texto, re.I)
    if mm:
        rid = f"{mm.group(1)} No.{mm.group(2)}"
        merc, tipo = (mm.group(1).upper().split("_") + [tipo])[:2]
    tc = None
    mm = re.search(r"1\s*USD\s*=\s*L?\.?\s*([\d.,]+)", texto, re.I)
    if mm:
        tc = common.parse_numero(mm.group(1).replace(",", "."))
    mercado, ciudad = MERCADOS.get(merc, (None, None))
    mm = re.search(r"^(Mercado [^\n]+)$", texto, re.M)
    if mm:
        mercado = common.limpia_espacios(mm.group(1))
    mm = re.search(r"^Ciudad ([^\n]+)$", texto, re.M)
    if mm:
        ciudad = common.limpia_espacios(mm.group(1))
    return {"fecha": common.fecha_es_a_iso(texto), "reporte_id": rid, "tc": tc,
            "mercado": mercado, "ciudad": ciudad, "tipo": tipo}


_NUM = re.compile(r"^-?[\d,]+(\.\d+)?$")


def _es_num(c: str) -> bool:
    return bool(c) and bool(_NUM.match(c.replace(" ", "")))


_ENC = {"producto", "origen", "tamano", "unidad de venta", "unidad de", "venta",
        "precios", "rango", "bajo", "alto", "moda", "rango moda", "lempiras"}


def extrae(pdf_path: Path, url: str | None = None) -> dict:
    import pdfplumber

    regs = []
    with pdfplumber.open(pdf_path) as pdf:
        texto = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
        meta = _meta(texto, pdf_path.name if not url else url)
        pista, segmento, con_tamano = TIPOS.get(meta["tipo"], ("hortalizas", "mayorista", True))
        for page in pdf.pages:
            for tabla in page.extract_tables() or []:
                for row in tabla:
                    celdas = [(c.replace("\n", " ").strip() if c else "") for c in row]
                    if not any(celdas) or common.normaliza_texto(celdas[0]) in _ENC:
                        continue
                    nums = [common.parse_numero(c) for c in celdas if _es_num(c)]
                    # columnas de texto = todo lo anterior a la primera celda numérica
                    k = next((i for i, c in enumerate(celdas)
                              if _es_num(c)), len(celdas))
                    txt = celdas[:k] + [""] * 4
                    if not nums or not txt[0]:
                        continue
                    if con_tamano:
                        producto, origen, tamano, unidad = txt[:4]
                    else:
                        producto, origen, unidad = txt[:3]
                        tamano = None
                    if len(nums) >= 4:
                        pmin, pmax, mb, ma = nums[:4]
                        pmoda = (mb + ma) / 2
                    else:  # precio único
                        pmin, pmax = nums[0], nums[-1]
                        pmoda = (pmin + pmax) / 2
                    cm = re.search(r"(CAT\s*\d+|Clase\s*[IVX]+|de primera|de segunda)", producto, re.I)
                    regs.append(common.construye_registro(
                        pais=PAIS, fecha=meta["fecha"], fuente=FUENTE,
                        mercado=meta["mercado"], ciudad=meta["ciudad"], segmento=segmento,
                        categoria=pista, producto=producto, calidad=cm.group(1) if cm else None,
                        tamano=tamano or None, origen=origen or None, unidad_venta=unidad or None,
                        moneda=MONEDA, precio_min=pmin, precio_max=pmax, precio_moda=pmoda,
                        url_fuente=url or PAGINA, reporte_id=meta["reporte_id"],
                        _pista_categoria=pista))
    for r in regs:
        r["categoria"] = common.clasifica_categoria(r["producto"], pista)
    return {**meta, "n": len(regs), "registros": regs}


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", nargs="+", help="PDFs locales (pruebas)")
    ap.add_argument("--desde", help="AAAA-MM-DD (por defecto: día siguiente a lo último en la base)")
    ap.add_argument("--out", help="ruta de salida .json")
    args = ap.parse_args()

    carpeta = common.carpeta_datos()
    staging = carpeta / "staging"
    staging.mkdir(parents=True, exist_ok=True)

    reportes, fallas = [], []
    if args.pdf:
        for p in args.pdf:
            reportes.append(extrae(Path(p)))
    else:
        hoy = date.today()
        if args.desde:
            desde = date.fromisoformat(args.desde)
        else:
            ult = _ultima_fecha_db()
            desde = (ult + timedelta(days=1)) if ult else hoy - timedelta(days=7)
        desde = max(desde, hoy - timedelta(days=60))
        lista = lista_reportes(desde)
        print(f"[HN] {len(lista)} reportes SIMPAH desde {desde}")
        for it in lista:
            dest = staging / f"hn_{Path(it['url']).name}"
            try:
                descarga(it["url"], dest)
                d = extrae(dest, it["url"])
                reportes.append(d)
                print(f"[HN]   {d['fecha']} {d['reporte_id']}: {d['n']} filas")
            except Exception as e:  # un PDF malo no tumba la corrida
                fallas.append(f"{it['url']}: {e}")
                print(f"[HN]   ERROR {it['url']}: {e}", file=sys.stderr)

    registros = [r for d in reportes for r in d["registros"]]
    fechas = sorted(d["fecha"] for d in reportes if d["fecha"])
    tcs = [d["tc"] for d in reportes if d.get("tc")]
    data = {"pais": PAIS, "fuente": FUENTE, "url": PAGINA,
            "fecha": fechas[-1] if fechas else None,
            "reportes": [{k: d[k] for k in ("fecha", "reporte_id", "mercado", "tipo", "n")} for d in reportes],
            "tc_usd_hnl_pdf": tcs[-1] if tcs else None,
            "n": len(registros), "fallas": fallas, "registros": registros}
    out = Path(args.out) if args.out else staging / "hn.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[HN] reportes={len(reportes)} registros={len(registros)} "
          f"ultima_fecha={data['fecha']} tc={data['tc_usd_hnl_pdf']} -> {out}")
    if not reportes:
        print("[HN] sin reportes nuevos (normal en fin de semana/feriado)")
        return 0
    if not registros:
        print("[HN] ERROR: 0 registros (¿cambió el layout del PDF?)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
