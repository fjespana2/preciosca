"""
Nicaragua — Bolsagro, "Precios Nacionales Agropecuarios de referencia".

Fuente: https://www.bolsagro.com.ni/estadisticas/precios-nacionales/59-precios-agropecuarios.html
Formato: la página incrusta 5 IMÁGENES PNG (tablas digitales limpias), una por bloque:

  MAYORISTA   -> granos básicos al por mayor,  Mercado Oriental
  MINORISTA   -> granos básicos al por menor,  Mercado Oriental
  PECUARIOS   -> carnes / lácteos / mariscos / otros (al por menor), Mercado Oriental
  HORTALIZAS  -> hortalizas al por mayor,      Mercado Mayoreo
  FRUTAS      -> frutas al por mayor,          Mercado Mayoreo

No hay CSV/PDF: los precios SOLO existen como texto dentro del PNG. Por eso este paso
NO extrae: descarga las imágenes y deja una plantilla para que Claude (visión) las
transcriba. Luego `nicaragua_ingest.py` valida y normaliza esa transcripción.

Uso:
  python nicaragua_fetch.py     # descarga PNGs a imagenes/ y escribe staging/ni_PLANTILLA.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

URL = "https://www.bolsagro.com.ni/estadisticas/precios-nacionales/59-precios-agropecuarios.html"
PAIS = "Nicaragua"
FUENTE = "Bolsagro"
MONEDA = "NIO"

# clasificación por nombre de archivo -> (segmento, categoria, mercado)
BLOQUES = {
    "mayorista": ("mayorista", "granos", "Mercado Oriental"),
    "minorista": ("minorista", "granos", "Mercado Oriental"),
    "pecuarios": ("minorista", "pecuarios", "Mercado Oriental"),
    "hortalizas": ("mayorista", "hortalizas", "Mercado Mayoreo"),
    "frutas": ("mayorista", "frutas", "Mercado Mayoreo"),
}


def _bloque(nombre: str) -> str | None:
    n = common.normaliza_texto(nombre)
    for k in BLOQUES:
        if k in n:
            return k
    return None


def main() -> int:
    carpeta = common.carpeta_datos()
    r = requests.get(URL, timeout=60, headers={"User-Agent": "precios-ca3/1.0"})
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "lxml")

    body = soup.select_one('[itemprop="articleBody"]') or soup
    fecha_txt = ""
    for h in body.find_all(["h1", "h2", "h3", "h4"]):
        if common.fecha_es_a_iso(h.get_text()):
            fecha_txt = h.get_text(strip=True)
            break
    fecha = common.fecha_es_a_iso(fecha_txt) or common.fecha_es_a_iso(r.text)

    imgs = []
    for img in body.find_all("img"):
        src = img.get("src") or ""
        if not re.search(r"\.(png|jpe?g)$", src, re.I):
            continue
        bloque = _bloque(src) or _bloque(img.get("alt") or "")
        if not bloque:
            continue
        full = urljoin(URL, src)
        destino = carpeta / "imagenes" / f"ni_{bloque}_{fecha or 'sf'}.png"
        ir = requests.get(full, timeout=60, headers={"User-Agent": "precios-ca3/1.0"})
        ir.raise_for_status()
        destino.write_bytes(ir.content)
        seg, cat, mercado = BLOQUES[bloque]
        imgs.append({
            "bloque": bloque, "url": full, "archivo": str(destino),
            "segmento": seg, "categoria": cat, "mercado": mercado,
        })

    plantilla = {
        "pais": PAIS, "fuente": FUENTE, "url": URL,
        "fecha": fecha, "fecha_texto": fecha_txt, "moneda": MONEDA,
        "_INSTRUCCIONES": (
            "Claude: abre cada archivo de 'imagenes' con la herramienta Read y transcribe "
            "TODAS las filas que tengan precio. Guarda staging/ni.json con SOLO dos claves: "
            "'fecha' (cópiala de aquí) y 'registros'. Cada registro es un objeto con: "
            "'bloque' (uno de: mayorista, minorista, pecuarios, hortalizas, frutas), "
            "'producto', 'unidad_venta' (texto completo tal cual, CON el paréntesis de "
            "peso p.ej. 'Quintal (100 lb)'), 'precio_prom' (número). Opcionales: 'tamano' "
            "y, sólo en PECUARIOS, 'subcategoria' = el encabezado en negrita "
            "(Carnes/Lácteos/Mariscos/Otros) que precede a esa fila. NO copies "
            "segmento/categoria/mercado: el script los deriva del 'bloque'. En hortalizas "
            "y frutas la 1.ª columna tras el producto es el TAMAÑO (aunque el encabezado "
            "diga 'Unidad de venta'); la 2.ª es la unidad_venta real. NO inventes filas ni "
            "precios; si la celda de precio está vacía, omite la fila."
        ),
        "imagenes": imgs,
        "registros": [],
    }
    out = carpeta / "staging" / "ni_PLANTILLA.json"
    out.write_text(json.dumps(plantilla, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[NI] fecha={fecha}  imagenes={len(imgs)}  -> {out}")
    for i in imgs:
        print(f"     - {i['bloque']:11s} {i['archivo']}")
    if not imgs:
        print("[NI] ERROR: no se encontraron imágenes de precios (¿cambió la página?)",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
