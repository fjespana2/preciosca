#!/usr/bin/env bash
# Corrida diaria LOCAL (la red de tu Mac sí llega a las fuentes).
# Lo invoca ~/Library/LaunchAgents/com.agrocentro.preciosca.plist
set -uo pipefail
cd "$(dirname "$0")"
unset CLAUDECODE CLAUDE_CODE_SSE_PORT 2>/dev/null || true
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

exec >> data/logs/cron.log 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="

git pull --quiet --rebase origin main 2>/dev/null || true
python3 -m pip install --quiet -r requirements.txt 2>/dev/null || true

claude -p "Ejecutá la recolección diaria de la skill precios-agropecuarios-ca3 para hoy. Pasos: (1) corré 'python3 .claude/skills/precios-agropecuarios-ca3/scripts/run_daily.py fetch'. (2) Abrí cada PNG de data/imagenes/ listado en data/staging/ni_PLANTILLA.json y transcribí las filas con precio a data/staging/ni.json (solo claves 'fecha' y 'registros'; cada registro con bloque, producto, unidad_venta con el paréntesis de peso, precio_prom, y opcionalmente tamano y subcategoria). (3) corré 'python3 .claude/skills/precios-agropecuarios-ca3/scripts/run_daily.py ingest'. (4) Si 'git status --porcelain data/' muestra cambios: git add data/ && git commit -m \"Precios \$(date +%F)\" && git push origin main. (5) Imprimí el resumen del log: fechas de reporte y filas nuevas/actualizadas por país." \
  --permission-mode bypassPermissions --allowedTools "Bash Read Write Edit"

echo "----- fin $(date '+%H:%M:%S') -----"
