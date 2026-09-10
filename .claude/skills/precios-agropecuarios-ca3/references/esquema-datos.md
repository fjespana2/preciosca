# Esquema de datos y diccionario de variables

Formato **largo / tidy**: una fila = un precio observado para un producto, en un
mercado, una unidad de venta y una fecha. Es el formato correcto para series de
tiempo, promedios por categoría, comparaciones entre países y modelos.

## Tabla `registros`

| Columna | Tipo | Descripción | Ejemplo |
|---|---|---|---|
| `id` | int | PK autoincremental | 1041 |
| `pais` | texto | `Guatemala` \| `Honduras` \| `Nicaragua` | `Honduras` |
| `fecha` | fecha ISO | **Fecha del reporte** (no la de descarga). Cada país a su ritmo. | `2026-08-24` |
| `fuente` | texto | `MAGA` \| `SIMPAH` \| `Bolsagro` | `SIMPAH` |
| `mercado` | texto | Mercado físico de referencia | `Mercado Central de Abastos de Sula` |
| `ciudad` | texto | Ciudad del mercado | `San Pedro Sula` |
| `segmento` | texto | `mayorista` \| `minorista` | `mayorista` |
| `categoria` | texto | `granos` `hortalizas` `frutas` `carnes` `lacteos` `huevos` `pesca` `abarrotes` `otros` (clasificador por nombre) | `hortalizas` |
| `subcategoria` | texto | Sólo Nicaragua/pecuarios: encabezado de la imagen | `Mariscos` |
| `producto` | texto | Nombre **tal cual** la fuente, sin recortar | `Tomate pera pintón` |
| `producto_norm` | texto | `producto` en minúsculas, sin tildes, para joins entre países | `tomate pera pinton` |
| `variedad` | texto | Reservado (hoy casi siempre NULL; la variedad va en `producto`) | |
| `calidad` | texto | `de primera` / `CAT 1` / `Clase I` si aparece | `CAT 1` |
| `tamano` | texto | `Grande` `Mediano` `Pequeño` `Mixto` `Calibre 50-55 mm` … | `Mediano` |
| `origen` | texto | Procedencia del producto. **Sólo Honduras** la publica. | `Siguatepeque` |
| `unidad_venta` | texto | Unidad comercial original, con su paréntesis de peso | `Caja de cartón (25 lb)` |
| `unidad_tipo` | texto | Unidad normalizada (`quintal` `arroba` `libra` `caja` `saco` `docena` `ciento` `litro` …) | `caja` |
| `cantidad_lb` | real | Libras que contiene esa unidad. **NULL si la fuente no da el peso.** | `25.0` |
| `moneda` | texto | `GTQ` (quetzal) \| `HNL` (lempira) \| `NIO` (córdoba) | `HNL` |
| `precio_min` | real | Extremo bajo del rango (o precio único) | `230.00` |
| `precio_max` | real | Extremo alto del rango (o precio único) | `250.00` |
| `precio_moda` | real | Precio moda. Sólo Honduras. Promedio de moda-bajo y moda-alto. | `230.00` |
| `precio_prom` | real | Precio promedio. Sólo Nicaragua lo publica directo. | `550.00` |
| `precio_ref` | real | **Precio representativo, úsalo para análisis.** Prioridad: moda → promedio → punto medio del rango → valor único. | `240.00` |
| `precio_lb_local` | real | `precio_ref / cantidad_lb`, en moneda local. NULL si `cantidad_lb` es NULL. | `9.60` |
| `tc_usd` | real | Unidades de moneda local por **1 USD**, del día de la corrida | `26.8118` |
| `precio_ref_usd` | real | `precio_ref / tc_usd` | `8.95` |
| `precio_lb_usd` | real | `precio_lb_local / tc_usd` — **la única columna comparable entre los 3 países** | `0.358` |
| `url_fuente` | texto | URL de la que se extrajo | |
| `reporte_id` | texto | Identificador del reporte (Honduras: `SPSCA_HOR No.149`) | |
| `hash` | texto | SHA1(16) de `pais+fecha+segmento+mercado+producto+tamano+origen+unidad_venta`. **UNIQUE** → deduplicación. | `a3f1…` |
| `capturado_en` | timestamp | Cuándo se ejecutó la extracción | `2026-09-10T06:32:11` |

### Índice único y deduplicación

`ux_registros_hash` sobre `hash`. La ingesta hace `INSERT … ON CONFLICT(hash) DO
UPDATE`: si el mismo producto/fecha/unidad ya existe, se **actualiza** (precio y
tipo de cambio) en vez de duplicar. Por eso es seguro correr la skill varias
veces al día o reprocesar un reporte viejo.

## Tabla `corridas` (bitácora)

`fecha_reporte`, `ejecutado_en`, `gt_filas`, `hn_filas`, `ni_filas`,
`filas_nuevas`, `filas_actualizadas`, `tc_gtq`, `tc_hnl`, `tc_nio`,
`tc_fallback` (1 = se usaron tasas de respaldo), `errores`, `notas`.

Sirve para auditar continuidad de la serie: días sin corrida, fuentes que
dejaron de aportar, saltos de tipo de cambio.

## Variables recomendadas para análisis estadístico

- **Serie de tiempo de un producto**: filtra `producto_norm`, `pais`, `segmento`,
  `unidad_tipo` constante; grafica `precio_ref` (misma moneda/unidad) o
  `precio_lb_local`.
- **Comparar países**: usa `precio_lb_usd`. Es lo único homogéneo (misma unidad
  física, misma moneda). Ojo: mayorista vs minorista no son comparables.
- **Inflación de canasta**: promedia `precio_lb_local` ponderando por categoría, o
  arma un índice base 100 con la primera fecha disponible.
- **Volatilidad**: desviación estándar de `precio_ref` en ventana móvil; el ancho
  del rango `precio_max - precio_min` es una proxy de dispersión intradía.
- **Estacionalidad**: `strftime('%m', fecha)` para efectos de mes; cosecha de
  granos e invierno mueven fuerte hortalizas.
- **Calidad del dato**: cuenta filas por `fecha` y `pais`; una caída brusca suele
  significar cambio de formato en la fuente, no cambio de mercado.

## Consultas SQL de ejemplo

```sql
-- Precio mayorista del tomate por país, últimos 30 días
SELECT fecha, pais, precio_lb_usd
FROM registros
WHERE producto_norm LIKE '%tomate%' AND segmento='mayorista'
  AND fecha >= date('now','-30 day')
ORDER BY fecha;

-- Continuidad: filas por país y día
SELECT fecha, pais, COUNT(*) n
FROM registros GROUP BY fecha, pais ORDER BY fecha DESC;

-- Canasta de granos básicos (GTQ/lb) en Guatemala
SELECT fecha, AVG(precio_lb_local) gtq_por_lb
FROM registros
WHERE pais='Guatemala' AND categoria='granos' AND cantidad_lb IS NOT NULL
GROUP BY fecha ORDER BY fecha;
```
