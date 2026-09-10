---
name: precios-agropecuarios-ca3
description: >-
  Recolecta y acumula los precios diarios de productos agropecuarios de los
  reportes oficiales de Guatemala (MAGA), Honduras (SIMPAH/FHIA) y Nicaragua
  (Bolsagro) en una base de datos SQLite + CSV, con variables listas para análisis
  estadístico (precio representativo, precio por libra, conversión a USD,
  categoría, mercado, origen, segmento mayorista/minorista). Úsala siempre que el
  usuario pida bajar / actualizar / recopilar "los precios de hoy", correr la
  recolección o el pipeline de precios (completo o de un solo país), alimentar o
  mantener la base de precios de Centroamérica, transcribir las imágenes de
  Bolsagro, o programar esa recolección para que corra a diario. Úsala también
  cuando pida consultar o analizar sobre esos datos ya guardados: series de
  tiempo, evolución o comparación de precios de granos, hortalizas, frutas o
  pecuarios por producto, mercado o país en GT/HN/NI. Cubre los tres países aunque
  el usuario nombre solo uno o un solo producto. NO es para precios internacionales
  de bolsa (café/azúcar en Nueva York), aranceles o comercio exterior, ni para
  reportes ya elaborados como TAM News o la Perspectiva Agroclimática.
---

# Precios agropecuarios CA-3 (Guatemala · Honduras · Nicaragua)

## Qué hace

Extrae el reporte de precios **del día vigente** de tres fuentes oficiales, lo
convierte a un formato largo (tidy) con una fila por producto/mercado/unidad, y
lo agrega a una base acumulada. Ninguna fuente publica histórico: la serie se
construye corriendo esto **todos los días**.

| País | Fuente | Formato | Cómo se extrae |
|---|---|---|---|
| 🇬🇹 Guatemala | MAGA – Precios diarios al mayorista | Tabla HTML | `requests` + BeautifulSoup (determinista) |
| 🇭🇳 Honduras | SIMPAH (SAG) vía FHIA – Reporte diario mayorista | PDF de texto | `pdfplumber.extract_table` (determinista) |
| 🇳🇮 Nicaragua | Bolsagro – Precios nacionales | **5 imágenes PNG** | Claude transcribe las tablas con visión, un script valida |

Guatemala y Honduras se procesan solos. **Nicaragua exige que Claude lea las
imágenes** — no hay texto que un script pueda parsear.

## Dónde viven los datos

Carpeta configurable con la variable de entorno `PRECIOS_CA3_HOME`
(por defecto `~/precios-agropecuarios-ca3/`):

```
precios_ca3.sqlite          tabla `registros` (histórico) + `corridas` (bitácora)
export/precios_ca3.csv      todo el histórico, formato largo — para Excel/Power BI/R
export/precios_guatemala.csv  · precios_honduras.csv · precios_nicaragua.csv
staging/                    JSON intermedios de la corrida en curso
imagenes/                   PNGs de Nicaragua descargados
logs/run_AAAA-MM-DD.json    resumen de cada corrida
```

El esquema completo y el diccionario de variables está en
`references/esquema-datos.md`. Léelo si el usuario va a analizar los datos o
pregunta qué significa una columna.

## Requisito único

`pdfplumber` (para Honduras). Si falta, instálalo antes de correr:

```bash
python3 -m pip install --quiet pdfplumber requests beautifulsoup4 lxml
```

## Flujo de la recolección diaria

Corre desde `scripts/`. Son dos fases porque Nicaragua necesita tu intervención.

### Fase 1 — descargar y parsear

```bash
python3 run_daily.py fetch
```

Esto deja:
- `staging/gt.json` y `staging/hn.json` — **ya listos** (registros normalizados).
- `staging/ni_PLANTILLA.json` — lista las 5 imágenes descargadas en `imagenes/` con
  su `bloque`, `segmento`, `categoria` y `mercado`.

### Fase 2 — transcribir Nicaragua (tú, Claude)

Abre **cada** imagen listada en la plantilla con la herramienta Read y transcribe
**todas las filas que tengan precio**. Escribe `staging/ni.json` con **solo dos
claves**: `fecha` (cópiala de la plantilla) y `registros`. Cada registro:

```json
{"bloque": "hortalizas", "producto": "Tomate pera", "tamano": "Mediano",
 "unidad_venta": "Cesta plástica (45-50 lb)", "precio_prom": 550}
```

- `bloque` (obligatorio): uno de `mayorista`, `minorista`, `pecuarios`,
  `hortalizas`, `frutas`. El script deriva de ahí `segmento`, `categoria` y
  `mercado` — **no los copies**.
- `unidad_venta`: cópiala completa, con el paréntesis de peso (`"Quintal (100 lb)"`,
  `"Cien und (70-80 lb)"`). Ese paréntesis es lo que permite el precio por libra.
- `tamano` (opcional): en **hortalizas y frutas** la 1.ª columna tras el producto
  (aunque el encabezado diga "Unidad de venta") es el tamaño; la 2.ª es la
  `unidad_venta` real.
- `subcategoria` (solo **pecuarios**): el renglón en negrita sin precio (`Carnes`,
  `Lácteos`, `Mariscos`, `Otros`) que encabeza el grupo. No lo transcribas como
  producto.
- No inventes filas ni precios. Si la celda de precio está vacía, omite la fila.

### Fase 3 — normalizar, enriquecer y guardar

```bash
python3 run_daily.py ingest
```

Esto normaliza Nicaragua, trae el tipo de cambio USD del día, hace el
**upsert** en SQLite (correr dos veces el mismo día actualiza, no duplica),
regenera los CSV, escribe `logs/run_<fecha_hora>.json` (uno por corrida, no se
pisa) y agrega una línea a `logs/historial.jsonl`.

### Reportar al usuario

El JSON que imprime `db.py ingest` (y el log de la corrida) trae
`filas_nuevas_por_pais` y `filas_actualizadas_por_pais`. Resume: fecha del
reporte de cada país, filas nuevas vs actualizadas **por país**, si `tc_fallback`
fue true, y cualquier error. Menciona explícitamente si un país no aportó filas
nuevas (su reporte no cambió desde la última corrida — normal, ver abajo).

## Cosas que van a pasar y no son error

- **Los tres países reportan en fechas distintas.** MAGA es diario; el PDF de
  SIMPAH y las imágenes de Bolsagro a veces traen la fecha de hace días. Cada fila
  guarda **su** fecha de reporte (`registros.fecha`). Si un reporte no cambió
  desde ayer, el upsert no crea filas nuevas — eso es correcto, no lo fuerces.
- **`cantidad_lb` / `precio_lb_local` en blanco.** Pasa cuando la unidad no dice el
  peso (`Ciento`, `Docena`, `Mazo` sin paréntesis). Se deja `NULL` a propósito; no
  adivines.
- **`tc_fallback: true` en el log.** La API de tipo de cambio falló y se usaron
  tasas de respaldo (o la del PDF de Honduras). Avísale al usuario para que las
  revise.

## Si una fuente cambia de formato

Los extractores fallan con un mensaje claro (`0 registros`, `no se pudo leer la
fecha`). Detalles de cada fuente, URLs alternativas y quirks en
`references/fuentes.md`. El mapa de unidades → libras está en
`references/conversiones-unidades.md`.

## Programación diaria

Para que corra sola, usa la skill `schedule` (agente en la nube) o `/loop`. El
prompt del agente programado debe ser algo como:

> Ejecuta la skill precios-agropecuarios-ca3 para hoy: corre `run_daily.py fetch`,
> transcribe las imágenes de Nicaragua a `staging/ni.json`, corre
> `run_daily.py ingest` y dime el resumen del log.

Sugiere una hora entre 6:00 y 7:00 a.m. hora de Centroamérica, cuando ya
publicaron los reportes del día.
