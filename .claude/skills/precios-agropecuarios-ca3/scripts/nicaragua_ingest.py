"""
Nicaragua — valida y normaliza la transcripción hecha por Claude (staging/ni.json)
y la convierte en registros canónicos -> staging/ni_registros.json

Espera un JSON con la forma de staging/ni_PLANTILLA.json, con 'registros' lleno:
  { "bloque": "hortalizas", "producto": "Tomate pera", "tamano": "Mediano",
    "unidad_venta": "Cesta plástica (45-50 lb)", "precio_prom": 550,
    "subcategoria": null }

Uso:
  python nicaragua_ingest.py                     # lee staging/ni.json
  python nicaragua_ingest.py --in otro.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402
from nicaragua_fetch import BLOQUES, PAIS, FUENTE, MONEDA, URL  # noqa: E402


def normaliza(data: dict) -> dict:
    fecha = common.fecha_es_a_iso(str(data.get("fecha") or data.get("fecha_texto") or ""))
    registros = []
    problemas = []

    for i, row in enumerate(data.get("registros", [])):
        bloque = common.normaliza_texto(row.get("bloque"))
        if bloque not in BLOQUES:
            problemas.append(f"fila {i}: bloque desconocido {row.get('bloque')!r}")
            continue
        seg, cat, mercado = BLOQUES[bloque]
        # la fila puede sobreescribir mercado/segmento/categoria si venían en la plantilla
        seg = row.get("segmento") or seg
        cat = row.get("categoria") or cat
        mercado = row.get("mercado") or mercado

        precio = common.parse_numero(row.get("precio_prom") or row.get("precio"))
        if precio is None:
            continue  # fila sin precio: se omite en silencio (encabezados, etc.)

        # para pecuarios, la subcategoría de la imagen (Carnes/Lácteos/Mariscos)
        # es mejor pista que el bloque; "Otros" no dice nada -> clasificar por nombre
        subcat = row.get("subcategoria")
        pista = subcat if (cat == "pecuarios" and subcat) else cat

        r = common.construye_registro(
            pais=PAIS, fecha=fecha, fuente=FUENTE,
            mercado=mercado, ciudad="Managua", segmento=seg,
            categoria=cat if cat != "pecuarios" else None,  # deja que el clasificador afine carnes/lacteos/pesca/huevos
            subcategoria=subcat,
            producto=row.get("producto"), tamano=row.get("tamano"),
            unidad_venta=row.get("unidad_venta"), moneda=MONEDA,
            precio_prom=precio, precio_min=precio, precio_max=precio,
            url_fuente=URL,
            _pista_categoria=pista,
        )
        errs = common.valida_registro(r)
        if errs:
            problemas.append(f"fila {i} ({r.get('producto')}): {', '.join(errs)}")
            continue
        registros.append(r)

    return {
        "pais": PAIS, "fuente": FUENTE, "url": URL, "fecha": fecha,
        "n": len(registros), "problemas": problemas, "registros": registros,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="entrada", help="ruta a ni.json")
    ap.add_argument("--out", help="ruta de salida")
    args = ap.parse_args()

    carpeta = common.carpeta_datos()
    entrada = Path(args.entrada) if args.entrada else carpeta / "staging" / "ni.json"
    if not entrada.exists():
        print(f"[NI] ERROR: falta {entrada}. Claude debe transcribir las imágenes "
              f"a partir de staging/ni_PLANTILLA.json primero.", file=sys.stderr)
        return 1

    data = json.loads(entrada.read_text(encoding="utf-8"))
    res = normaliza(data)
    out = Path(args.out) if args.out else carpeta / "staging" / "ni_registros.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[NI] fecha={res['fecha']}  registros={res['n']}  "
          f"problemas={len(res['problemas'])}  -> {out}")
    for p in res["problemas"][:20]:
        print(f"     ! {p}", file=sys.stderr)
    if res["n"] == 0:
        print("[NI] ERROR: 0 registros normalizados", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
