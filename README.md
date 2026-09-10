# Precios agropecuarios CA-3 — base de datos

Recolección diaria de precios de productos agropecuarios de:

| País | Fuente | Reporte |
|---|---|---|
| 🇬🇹 Guatemala | MAGA | Precios diarios al mayorista (HTML) |
| 🇭🇳 Honduras | SIMPAH / FHIA | Reporte diario mayorista (PDF) |
| 🇳🇮 Nicaragua | Bolsagro | Precios nacionales (imágenes PNG) |

## Estructura

```
.claude/skills/precios-agropecuarios-ca3/   la skill (lógica de extracción y normalización)
data/
├── precios_ca3.sqlite      base acumulada — tabla `registros` (histórico) + `corridas` (bitácora)
├── export/*.csv            mismo contenido en CSV largo/tidy (para Excel, Power BI, R, pandas)
└── logs/                   una entrada por corrida + historial.jsonl
run_cloud.sh                lo ejecuta el agente programado
requirements.txt
```

`data/staging/` y `data/imagenes/` están en `.gitignore` (archivos de trabajo de cada corrida).

## Correr a mano (local)

```bash
pip install -r requirements.txt
python3 .claude/skills/precios-agropecuarios-ca3/scripts/run_daily.py fetch
#  -> transcribir data/imagenes/*.png a data/staging/ni.json  (lo hace Claude)
python3 .claude/skills/precios-agropecuarios-ca3/scripts/run_daily.py ingest
```

Cuando la skill vive dentro de este repo, la base se escribe en `data/`
automáticamente (detecta la raíz `.git`). Para usar otra carpeta:
`export PRECIOS_CA3_HOME=/ruta`.

## Automatización

Un agente programado (routine de Claude Code en la nube) clona este repo cada
mañana, corre el pipeline, y hace `git commit` de `data/` con los precios del día.

## Diccionario de variables

Ver `.claude/skills/precios-agropecuarios-ca3/references/esquema-datos.md`.
