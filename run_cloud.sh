#!/usr/bin/env bash
# Lo corre el agente en la nube. NO transcribe Nicaragua (eso lo hace Claude).
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install --quiet -r requirements.txt
python3 .claude/skills/precios-agropecuarios-ca3/scripts/run_daily.py fetch
echo ">>> Ahora Claude debe transcribir data/imagenes/*.png a data/staging/ni.json"
echo ">>> y luego: python3 .claude/skills/precios-agropecuarios-ca3/scripts/run_daily.py ingest"
