# Fuentes: detalle, quirks y qué hacer si cambian

## 🇬🇹 Guatemala — MAGA

- **URL**: https://precios.maga.gob.gt/diarios/diarios.html
- **Qué es**: "Precios de productos agropecuarios al mayorista en quetzales",
  Sistema de Información de Mercados del MAGA.
- **Formato**: HTML servido ya renderizado (no hay AJAX). La tabla
  `#listado_diarios` tiene `<thead>` fijo `Producto | Mercado | Medida | Precio` y
  el `<tbody>` con ~120 filas. DataTables sólo agrega paginación/exportación en el
  navegador; el HTML crudo ya trae todo.
- **Fecha**: en `<h5>` dentro de `#precios_diarios` y en `<title>` (`… 09/09/2026`).
- **Mercado**: siempre "La Terminal" (mercado mayorista de Ciudad de Guatemala).
- **Moneda**: GTQ. Sin rango: `precio_min = precio_max = precio`.
- **Quirks**:
  - El nombre trae variedad + tamaño + calidad separados por comas
    (`Aguacate Hass, mediano, de primera, importado`). Se deja íntegro en
    `producto`; se extraen `calidad` y `tamano` a sus columnas por regex.
  - Hay erratas ocasionales en la fuente (`de primerq`). No las corrijas.
  - Muchas unidades son por conteo (`Ciento`, `Docena`, `Mazo (20 trenzas)`) sin
    peso → `cantidad_lb` NULL.
- **Si cambia**: si `extract_guatemala.py` reporta 0 registros, revisar si
  cambió el `id` de la tabla o si migraron a una API JSON (mirar `Network` en el
  navegador). Reportes relacionados del mismo sitio: semanales en
  `https://precios.maga.gob.gt/` (no los usa esta skill).

## 🇭🇳 Honduras — SIMPAH (SAG)

- **Página**: https://sag.gob.hn/secciones/publicaciones/simpah/
- **Listado (API WordPress)**: `https://sag.gob.hn/wp-json/wp/v2/media?mime_type=application/pdf&after=AAAA-MM-DDT00:00:00&per_page=100`
- **Historia**: hasta el 24-ago-2026 se leía la copia de FHIA
  (`fhia.org.hn/.../2.1._reporte_diario_precios_hortalizas_central_abastos.pdf`).
  FHIA dejó de actualizarla; desde sep-2026 la SAG publica directo. No usar FHIA.
- **Nombre de archivo**: `<MERCADO>_<TIPO>_<AAAAMMDD>[-_]<No>.pdf`
  - MERCADO: `SPSCA` Central de Abastos de Sula (SPS), `SPSMC` Medina-Concepción (SPS),
    `TGAZB` Zonal Belén (Tegucigalpa)
  - TIPO: `HOR` hortalizas, `FRU` frutas, `GB` granos básicos mayorista,
    `GBMN` granos básicos minorista (se ignoran PEC, INS y otros)
- **Recuperación automática**: cada corrida baja todos los reportes con fecha
  posterior a la última de Honduras en la base (máx. 60 días). No hay que hacer
  nada si una corrida falla o cae en fin de semana.
- **Formato**: PDF de texto nativo. Columnas HOR/FRU: `Producto | Origen | Tamaño |
  Unidad | Rango bajo | Rango alto | Moda bajo | Moda alto`. GB/GBMN no traen Tamaño.
  Si sólo hay 2 números es precio único (min = max = moda).
- **Fecha**: encabezado `… Viernes, 23 de octubre de 2026`; `Código reporte:
  SPSCA_HOR, No. NNN` → `reporte_id`.
- **Moneda**: HNL. El pie del PDF trae `1 USD = 26.8476 HNL, fuente: Banco Central
  de Honduras` → se guarda como `tc_usd_hnl_pdf` y se usa de respaldo si la API de
  tipo de cambio falla.
- **Quirks**:
  - **La fecha suele venir atrasada varios días** respecto a hoy. Normal: el
    `hash` incluye la fecha, así que re-descargar el mismo PDF no duplica.
  - `Carga = 200 lb` (validado en reportes SIMPAH). Está en el mapa de unidades.
  - `origen` a veces es `lugar no especificado` o un país (`China`, `Holanda`).
- **Si cambia**: si `extract_honduras.py` da 0 registros, el PDF pasó a ser
  escaneado (imagen) → habría que OCR (no hay tesseract; usar visión de Claude
  como en Nicaragua) o `extract_tables` ya no reconoce la rejilla → revisar
  `page.extract_text()` y parsear por posición.

## 🇳🇮 Nicaragua — Bolsagro

- **URL**: https://www.bolsagro.com.ni/estadisticas/precios-nacionales/59-precios-agropecuarios.html
- **Qué es**: "Precios Agropecuarios de referencia" de Bolsa Agropecuaria de
  Nicaragua (Bolsagro).
- **Formato**: la página incrusta **5 imágenes PNG** en el `articleBody`. Los
  precios **sólo existen como texto dentro del PNG** — no hay tabla HTML, ni CSV,
  ni PDF. Por eso Claude las transcribe con visión.
- **Los 5 bloques** (por nombre de archivo):

  | Archivo contiene | segmento | categoria | mercado | Columnas en la imagen |
  |---|---|---|---|---|
  | `MAYORISTA` | mayorista | granos | Mercado Oriental | Producto · Unidad de venta · Precio promedio |
  | `MINORISTA` | minorista | granos | Mercado Oriental | Producto · Unidad de venta · Precio promedio |
  | `PECUARIOS` | minorista | (carnes/lácteos/pesca/otros) | Mercado Oriental | Producto · Unidad de venta · Precio promedio · **encabezados en negrita** = subcategoria |
  | `HORTALIZAS` | mayorista | hortalizas | Mercado Mayoreo | Producto · **Tamaño** (mal rotulado "Unidad de venta") · Unidad de venta · Precio promedio |
  | `FRUTAS` | mayorista | frutas | Mercado Mayoreo | Producto · Tamaño · Unidad de venta · Precio promedio |

- **Fecha**: en un `<h3>` del cuerpo (`Lunes 7 de septiembre 2026`) y en el nombre
  del archivo (`..._7_DE_SEPTIEMBRE_2026.png`).
- **Moneda**: NIO (córdoba). Sólo `precio_prom` (se copia a min/max).
- **Quirks**:
  - Nombres de archivo con dobles guiones bajos (`MINORISTA__7_DE_…`). El fetch
    normaliza por substring, no exige el nombre exacto.
  - Los cinco bloques son **disjuntos** (distinto segmento/categoría/mercado): no
    hay doble conteo entre `MAYORISTA` y `HORTALIZAS`.
  - `PECUARIOS` mezcla carnes, lácteos, mariscos y abarrotes ("Otros"): la
    `categoria` final la decide el clasificador por nombre, la `subcategoria`
    queda como venía en la imagen.
- **Si cambia**: si `nicaragua_fetch.py` no encuentra imágenes, revisar los
  `src`/`alt` de los `<img>` en el `articleBody`. Si Bolsagro empezara a publicar
  Excel/PDF, reescribir el fetch para bajarlo y el ingest para parsearlo
  (eliminando el paso de transcripción).
- **Visto el 2026-10-13**: el sitio nombró los archivos de PECUARIOS y FRUTAS en
  singular (`pecuario_...png`, `fruta_...png`) en vez de plural, y publicó un
  `<img>` de MINORISTA duplicado (uno con el día en el nombre, otro sin fecha —
  probablemente un enlace viejo cacheado). `nicaragua_fetch.py` ya normaliza el
  singular/plural (`ALIASES`) y prefiere, por bloque, el `src` que trae un
  dígito (el día). Además, ese día **no había ninguna imagen de MAYORISTA**: el
  archivo nombrado `minorista_...png` contenía en realidad la tabla
  "Precios de venta **al por mayor** de granos básicos" (el título visible en
  la imagen, no el nombre del archivo, decide el bloque real). Claude debe
  siempre confirmar el bloque leyendo el título dentro de la imagen y
  corregirlo si no coincide con el nombre de archivo/plantilla.
- **Visto el 2026-10-18**: el sitio nombró el archivo de HORTALIZAS con un typo
  (`HORTALZIAS__...png`, falta la "I"), por lo que el match por substring
  `"hortalizas"` no lo encontraba y la plantilla salía con solo 4 imágenes.
  `nicaragua_fetch.py` ya mapea `"hortalzias"` → `hortalizas` en `ALIASES`.

## Tipo de cambio

- **Primario**: `https://open.er-api.com/v6/latest/USD` (gratis, sin llave, ~1
  actualización/día). Campos `rates.GTQ`, `rates.HNL`, `rates.NIO`.
- **Respaldo HNL**: tasa del BCH incrustada en el PDF de Honduras.
- **Último recurso**: constantes en `fx.py::_FALLBACK` (revisar y actualizar cada
  cierto tiempo). Cuando se usan, `corridas.tc_fallback = 1`.
