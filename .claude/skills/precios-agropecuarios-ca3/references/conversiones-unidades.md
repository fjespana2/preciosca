# Conversión de unidades de venta → libras

`common.unidad_a_libras()` devuelve `(unidad_tipo, cantidad_lb)`. El objetivo es
`precio_lb_local` y de ahí `precio_lb_usd`, la única métrica comparable entre los
tres países. **Cuando el peso no es inequívoco, `cantidad_lb` queda NULL** — es
preferible un hueco honesto a un número inventado.

## Método (en orden)

1. **Peso explícito en el texto de la unidad.** Regex sobre paréntesis:
   `(\d+(?:[-a]\d+)?)\s*(lb|kg|g|oz)`. Si es rango (`45-50 lb`) se toma el punto
   medio. `kg`→×2.20462, `g`→×0.00220462, `oz`→÷16.
   - `Cien und (70-80 lb)` → 75 lb
   - `Caja de cartón (5 kg)` → 11.0231 lb
   - `Mazo (30-40 g)` → 0.0772 lb
   - `Mazo (6-8 oz)` → 0.4375 lb

2. **Unidad "desnuda" con peso conocido** (sólo si no hubo paréntesis):

   | unidad | libras |
   |---|---|
   | Quintal, qq | 100 |
   | Carga (Honduras) | 200 |
   | Arroba, @ | 25 |
   | Libra, lb | 1 |
   | Onza | 0.0625 |
   | Kilogramo, kilo, kg | 2.20462 |
   | Gramo | 0.00220462 |
   | Tonelada | 2204.62 |

3. **Nada aplica** → `cantidad_lb = NULL`. Casos típicos: `Ciento`, `Cien und`
   (sin lb), `Docena` (sin lb), `Mazo`, `Mano`, `Bolsa`, `Caja`, `Saco`,
   `Canasto`, `Cesta` cuando no traen peso.

## `unidad_tipo` (normalización del nombre, independiente del peso)

Palabra clave detectada en el texto, para agrupar: `quintal`, `arroba`, `libra`,
`onza`, `kilogramo`, `gramo`, `tonelada`, `carga`, `caja`, `cajilla`, `saco`,
`costal`, `bulto`, `matate`, `maleta`, `canasto`, `canasta`, `cesta`, `bolsa`,
`mazo`, `mano`, `docena`, `ciento`, `cien`, `unidad`/`und`, `litro`, `galon`,
`envase`, `bandeja`, `red`, `malla`, `atado`, `manojo`, `trenza`, `mecate`.

Se usa para filtrar series homogéneas: comparar sólo filas con el mismo
`unidad_tipo` evita mezclar "precio del quintal" con "precio de la docena".

## Ampliar el mapa

Si aparece una unidad con peso fijo conocido y sin paréntesis (p.ej. una región
usa "matate" siempre = 80 lb), agrégala a `common._UNIDAD_LB`. Sólo hazlo si el
peso es **constante y verificable**; muchas unidades artesanales varían por
producto y deben quedar NULL.

## Notas de equivalencia (referencia, no todas están en el mapa)

- 1 quintal = 100 lb = 4 arrobas = 45.36 kg
- 1 arroba = 25 lb = 11.34 kg
- 1 carga (HN, granos) = 200 lb = 2 quintales
- 1 kg = 2.20462 lb
- "Cajilla" de huevo = 30 unidades (el peso lo da el paréntesis: ~3.3–3.75 lb)
