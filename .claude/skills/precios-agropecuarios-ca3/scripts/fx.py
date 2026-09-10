"""
Tipo de cambio USD -> {GTQ, HNL, NIO} del día.

Primario:  https://open.er-api.com/v6/latest/USD   (gratis, sin llave)
Respaldo:  tasa del BCH incrustada en el PDF de Honduras (solo HNL)
Último recurso: constantes con ADVERTENCIA (deben revisarse a mano)

Devuelve "unidades de moneda local por 1 USD". Para pasar a USD:
    precio_usd = precio_local / tc_usd
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

MONEDAS = ("GTQ", "HNL", "NIO")
# Último recurso — septiembre 2026. Revisar si se usan (se marca en el log de la corrida).
_FALLBACK = {"GTQ": 7.65, "HNL": 26.85, "NIO": 36.75}


def _api() -> dict | None:
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=30)
        r.raise_for_status()
        j = r.json()
        if j.get("result") != "success":
            return None
        return {m: float(j["rates"][m]) for m in MONEDAS}
    except Exception as e:  # noqa: BLE001
        print(f"[FX] API falló: {e}", file=sys.stderr)
        return None


def obtiene_tc(tc_hnl_respaldo: float | None = None) -> dict:
    """tc_hnl_respaldo: la tasa que trae el PDF de Honduras, si se tiene."""
    fuente = {}
    tasas = _api()
    if tasas:
        origen = "open.er-api.com"
    else:
        tasas = dict(_FALLBACK)
        origen = "FALLBACK (revisar a mano)"
        if tc_hnl_respaldo:
            tasas["HNL"] = tc_hnl_respaldo
            fuente["HNL"] = "PDF SIMPAH (BCH)"
    for m in MONEDAS:
        fuente.setdefault(m, origen)

    return {
        "fecha": date.today().isoformat(),
        "tasas": {m: round(tasas[m], 6) for m in MONEDAS},
        "fuente": fuente,
        "es_fallback": origen.startswith("FALLBACK"),
    }


def main() -> int:
    out = common.carpeta_datos() / "staging" / "fx.json"
    tc = obtiene_tc()
    out.write_text(json.dumps(tc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[FX] {tc['tasas']}  fallback={tc['es_fallback']}  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
