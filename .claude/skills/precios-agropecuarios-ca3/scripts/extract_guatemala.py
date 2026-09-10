"""
Guatemala — MAGA, "Precios diarios de productos agropecuarios al mayorista".

Fuente: https://precios.maga.gob.gt/diarios/diarios.html
Formato: tabla HTML estática, servida ya renderizada. Un solo mercado ("La Terminal").
Columnas de origen: Producto | Mercado | Medida | Precio   (moneda: GTQ)
La fecha viene en <h5> y en <title> ("... 09/09/2026").

El campo "Producto" trae variedad/tamaño/calidad juntos separados por comas, p.ej.:
  "Aguacate Hass, mediano, de primera, importado"
Lo dejamos íntegro en `producto` y además extraemos calidad ("de primera/segunda")
y tamaño ("grande/mediano/pequeño") a sus columnas, sin destruir el nombre.

Uso:
  python extract_guatemala.py            # escribe staging/gt.json
  python extract_guatemala.py --html f   # usa un HTML local (para pruebas)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

URL = "https://precios.maga.gob.gt/diarios/diarios.html"
PAIS = "Guatemala"
FUENTE = "MAGA"
MERCADO = "La Terminal"
CIUDAD = "Ciudad de Guatemala"
MONEDA = "GTQ"

_TAMANOS = ["extra grande", "grande", "mediano", "mediana", "pequeño", "pequeno",
            "pequeña", "chico", "primera", "segunda", "tercera"]


def _desglosa_producto(nombre: str) -> tuple[str | None, str | None]:
    """(calidad, tamano) a partir del nombre completo. El nombre NO se modifica."""
    n = common.normaliza_texto(nombre)
    calidad = None
    m = re.search(r"de (primera|segunda|tercera)", n)
    if m:
        calidad = f"de {m.group(1)}"
    tamano = None
    for t in ("extra grande", "grande", "mediano", "pequeno", "chico", "jumbo"):
        if re.search(rf"\b{t}\b", n):
            tamano = t
            break
    return calidad, tamano


def descarga_html() -> str:
    r = requests.get(URL, timeout=60, headers={"User-Agent": "precios-ca3/1.0"})
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def extrae(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    fecha_txt = ""
    h5 = soup.select_one("#precios_diarios h5")
    if h5:
        fecha_txt = h5.get_text(strip=True)
    if not fecha_txt and soup.title:
        fecha_txt = soup.title.get_text()
    fecha = common.fecha_es_a_iso(fecha_txt)

    tabla = soup.select_one("table#listado_diarios") or soup.find("table")
    registros = []
    if tabla:
        for tr in tabla.select("tbody tr"):
            celdas = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(celdas) < 4:
                continue
            producto, mercado, medida, precio = celdas[0], celdas[1], celdas[2], celdas[3]
            if not producto or common.parse_numero(precio) is None:
                continue
            calidad, tamano = _desglosa_producto(producto)
            registros.append(common.construye_registro(
                pais=PAIS, fecha=fecha, fuente=FUENTE,
                mercado=mercado or MERCADO, ciudad=CIUDAD,
                segmento="mayorista", producto=producto,
                calidad=calidad, tamano=tamano,
                unidad_venta=medida, moneda=MONEDA,
                precio_min=precio, precio_max=precio,
                url_fuente=URL,
            ))

    return {
        "pais": PAIS, "fuente": FUENTE, "url": URL,
        "fecha": fecha, "fecha_texto": fecha_txt,
        "n": len(registros), "registros": registros,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="ruta a HTML local (pruebas)")
    ap.add_argument("--out", help="ruta de salida .json")
    args = ap.parse_args()

    html = Path(args.html).read_text(encoding="utf-8") if args.html else descarga_html()
    data = extrae(html)

    out = Path(args.out) if args.out else common.carpeta_datos() / "staging" / "gt.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[GT] fecha={data['fecha']}  registros={data['n']}  -> {out}")
    if not data["fecha"]:
        print("[GT] ADVERTENCIA: no se pudo leer la fecha del reporte", file=sys.stderr)
    if data["n"] == 0:
        print("[GT] ERROR: 0 registros (¿cambió el HTML?)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
