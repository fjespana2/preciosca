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

## 🇭🇳 Honduras — SIMPAH (vía FHIA)

- **URL**: https://fhia.org.hn/wp-content/uploads/2.1._reporte_diario_precios_hortalizas_central_abastos.pdf
- **Qué es**: SIMPAH (Sistema de Información de Mercados de Productos Agrícolas de
  Honduras), Secretaría de Agricultura y Ganadería. FHIA lo re-publica.
- **Formato**: PDF de **texto nativo**, 2 páginas, 1 tabla.
  `pdfplumber.extract_table()` reconstruye celdas partidas en dos renglones
  (`Bajos de\nCholoma`). `pdftotext -layout` también sirve para inspección.
- **Columnas**: `Producto | Origen | Tamaño | Unidad de Venta | Rango Bajo |
  Rango Alto | Moda Bajo | Moda Alto`. Cuando no hay moda, esas 2 celdas van
  vacías y sólo queda el rango.
- **Fecha**: encabezado `… Lunes, 24 de agosto del 2026`. `Código reporte:
  SPSCA_HOR, No. NNN` → `reporte_id`.
- **Mercado**: "Mercado Central de Abastos de Sula", San Pedro Sula. Este archivo
  concreto (`2.1._…hortalizas…`) es **de hortalizas**.
- **Moneda**: HNL. El pie del PDF trae `1 USD = 26.8476 HNL, fuente: Banco Central
  de Honduras` → se guarda como `tc_usd_hnl_pdf` y se usa de respaldo si la API de
  tipo de cambio falla.
- **Quirks**:
  - **La fecha suele venir atrasada varios días** respecto a hoy. Normal: el
    `hash` incluye la fecha, así que re-descargar el mismo PDF no duplica.
  - `Carga = 200 lb` (validado en reportes SIMPAH). Está en el mapa de unidades.
  - `origen` a veces es `lugar no especificado` o un país (`China`, `Holanda`).
- **Otros reportes SIMPAH** (mismo patrón de nombre, por si se quieren agregar):
  `2.2._…`, `2.3._…` suelen ser otros mercados/segmentos en el mismo directorio
  `fhia.org.hn/wp-content/uploads/`. Para agregarlos, duplicar el extractor con la
  URL y el `mercado` correctos.
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

## Tipo de cambio

- **Primario**: `https://open.er-api.com/v6/latest/USD` (gratis, sin llave, ~1
  actualización/día). Campos `rates.GTQ`, `rates.HNL`, `rates.NIO`.
- **Respaldo HNL**: tasa del BCH incrustada en el PDF de Honduras.
- **Último recurso**: constantes en `fx.py::_FALLBACK` (revisar y actualizar cada
  cierto tiempo). Cuando se usan, `corridas.tc_fallback = 1`.
