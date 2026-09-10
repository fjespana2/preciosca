"""
Honduras — SIMPAH (SAG), "Reporte diario de precios de venta al por mayor".

Fuente (la que pasó el usuario):
  https://fhia.org.hn/wp-content/uploads/2.1._reporte_diario_precios_hortalizas_central_abastos.pdf
  -> Mercado Central Abastos de Sula, San Pedro Sula, Cortés.

Es un PDF de TEXTO NATIVO (no escaneado). pdfplumber.extract_table() reconstruye la
tabla incluso cuando una celda ocupa dos renglones ('Bajos de\nCholoma').

Columnas de origen:
  Producto | Origen | Tamaño | Unidad de Venta | Rango Bajo | Rango Alto | Moda Bajo | Moda Alto
Moneda: HNL (Lempira). El pie del PDF trae la tasa de cambio del BCH, que guardamos
como respaldo por si la API de tipo de cambio falla.

Encabezado: "Código reporte: SPSCA_HOR, No. 149 ... Lunes, 24 de agosto del 2026"

Uso:
  python extract_honduras.py             # descarga y escribe staging/hn.json
  python extract_honduras.py --pdf f     # usa un PDF local
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

URL = "https://fhia.org.hn/wp-content/uploads/2.1._reporte_diario_precios_hortalizas_central_abastos.pdf"
PAIS = "Honduras"
FUENTE = "SIMPAH"
MERCADO = "Mercado Central de Abastos de Sula"
CIUDAD = "San Pedro Sula"
MONEDA = "HNL"

_ENCABEZADOS = {"producto", "origen", "tamaño", "tamano", "unidad de venta",
                "precios", "rango", "bajo", "alto", "moda", "rango moda", "lempira"}


def descarga_pdf(destino: Path) -> Path:
    r = requests.get(URL, timeout=90, headers={"User-Agent": "precios-ca3/1.0"})
    r.raise_for_status()
    destino.write_bytes(r.content)
    return destino


def _texto_plano(pdf) -> str:
    return "\n".join((pg.extract_text() or "") for pg in pdf.pages)


def _meta(texto: str) -> dict:
    fecha = common.fecha_es_a_iso(texto)
    reporte_id = None
    m = re.search(r"C[oó]digo reporte:\s*([A-Z_]+),?\s*No\.?\s*(\d+)", texto, re.I)
    if m:
        reporte_id = f"{m.group(1)} No.{m.group(2)}"
    tc = None
    m = re.search(r"1\s*USD\s*=\s*([\d.,]+)\s*HNL", texto, re.I)
    if m:
        tc = common.parse_numero(m.group(1))
    mercado = MERCADO
    m = re.search(r"Mercado ([A-Za-zÁÉÍÓÚáéíóúñÑ ]+?)\n", texto)
    if m and "abast" in common.normaliza_texto(m.group(0)):
        mercado = common.limpia_espacios("Mercado " + m.group(1))
    return {"fecha": fecha, "reporte_id": reporte_id, "tc_pdf": tc, "mercado": mercado}


def _fila_valida(row: list) -> bool:
    celdas = [common.normaliza_texto(c) for c in row if c]
    if not celdas:
        return False
    if any(c in _ENCABEZADOS for c in celdas[:2]):
        return False
    # necesita al menos un número en las últimas 4 columnas
    return any(common.parse_numero(c) is not None for c in row[-4:])


def extrae(pdf_path: Path) -> dict:
    import pdfplumber

    registros = []
    with pdfplumber.open(pdf_path) as pdf:
        texto = _texto_plano(pdf)
        meta = _meta(texto)

        for page in pdf.pages:
            for tabla in page.extract_tables() or []:
                for row in tabla:
                    row = [(c.replace("\n", " ").strip() if c else None) for c in row]
                    while len(row) < 8:
                        row.append(None)
                    if not _fila_valida(row):
                        continue
                    producto, origen, tamano, unidad = row[0], row[1], row[2], row[3]
                    r_bajo, r_alto, m_bajo, m_alto = row[4], row[5], row[6], row[7]
                    if not producto:
                        continue

                    pmin = common.parse_numero(r_bajo)
                    pmax = common.parse_numero(r_alto)
                    # moda: promedio de moda bajo/alto si existen
                    mb, ma = common.parse_numero(m_bajo), common.parse_numero(m_alto)
                    pmoda = None
                    if mb is not None and ma is not None:
                        pmoda = (mb + ma) / 2.0
                    elif mb is not None:
                        pmoda = mb

                    calidad = None
                    cm = re.search(r"(CAT\s*\d+|Clase\s*[IVX]+|de primera|de segunda)",
                                   producto, re.I)
                    if cm:
                        calidad = cm.group(1)

                    registros.append(common.construye_registro(
                        pais=PAIS, fecha=meta["fecha"], fuente=FUENTE,
                        mercado=meta["mercado"], ciudad=CIUDAD, segmento="mayorista",
                        categoria="hortalizas",  # este reporte es de hortalizas; se reclasifica por producto si aplica
                        producto=producto, calidad=calidad, tamano=tamano,
                        origen=origen, unidad_venta=unidad, moneda=MONEDA,
                        precio_min=pmin, precio_max=pmax, precio_moda=pmoda,
                        url_fuente=URL, reporte_id=meta["reporte_id"],
                        _pista_categoria="hortalizas",
                    ))

    # reclasifica por nombre de producto (algunos no son hortaliza: papa, yuca, etc. sí lo son igual)
    for r in registros:
        r["categoria"] = common.clasifica_categoria(r["producto"], "hortalizas")

    return {
        "pais": PAIS, "fuente": FUENTE, "url": URL,
        "fecha": meta["fecha"], "reporte_id": meta["reporte_id"],
        "tc_usd_hnl_pdf": meta["tc_pdf"], "mercado": meta["mercado"],
        "n": len(registros), "registros": registros,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="ruta a PDF local (pruebas)")
    ap.add_argument("--out", help="ruta de salida .json")
    args = ap.parse_args()

    carpeta = common.carpeta_datos()
    if args.pdf:
        pdf_path = Path(args.pdf)
    else:
        pdf_path = carpeta / "staging" / "hn_reporte.pdf"
        descarga_pdf(pdf_path)

    data = extrae(pdf_path)
    out = Path(args.out) if args.out else carpeta / "staging" / "hn.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[HN] fecha={data['fecha']}  reporte={data['reporte_id']}  "
          f"registros={data['n']}  tc_pdf={data['tc_usd_hnl_pdf']}  -> {out}")
    if not data["fecha"]:
        print("[HN] ADVERTENCIA: no se pudo leer la fecha", file=sys.stderr)
    if data["n"] == 0:
        print("[HN] ERROR: 0 registros (¿cambió el layout del PDF?)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
