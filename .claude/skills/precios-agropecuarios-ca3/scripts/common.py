"""
Utilidades compartidas por los extractores de precios (Guatemala, Honduras, Nicaragua).

Todo lo que aquí se define es determinista y sin red, salvo `carpeta_datos()` que
solo resuelve rutas. La lógica de red vive en cada extractor y en fx.py.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from datetime import datetime, date
from pathlib import Path

# --------------------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------------------

def carpeta_datos() -> Path:
    """Carpeta donde vive la base de datos y los exports. Se resuelve así:

    1. variable de entorno PRECIOS_CA3_HOME (si está)
    2. si la skill vive dentro de un repo git -> <raíz del repo>/data
       (esto es lo que usa el agente en la nube: clona el repo y hace commit de data/)
    3. ~/precios-agropecuarios-ca3  (uso local por defecto)
    """
    raw = os.environ.get("PRECIOS_CA3_HOME")
    if raw:
        p = Path(raw).expanduser()
    else:
        here = Path(__file__).resolve()
        repo_data = next(
            (par / "data" for par in here.parents if (par / ".git").exists()), None
        )
        p = repo_data or Path("~/precios-agropecuarios-ca3").expanduser()
    (p / "staging").mkdir(parents=True, exist_ok=True)
    (p / "export").mkdir(parents=True, exist_ok=True)
    (p / "logs").mkdir(parents=True, exist_ok=True)
    (p / "imagenes").mkdir(parents=True, exist_ok=True)
    return p


# --------------------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------------------

def normaliza_texto(s: str | None) -> str:
    """minúsculas, sin tildes, espacios colapsados. Para joins y clasificación."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def limpia_espacios(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", str(s).replace("\n", " ")).strip()
    return s or None


# --------------------------------------------------------------------------------------
# Números
# --------------------------------------------------------------------------------------

def parse_numero(x) -> float | None:
    """'1,234.50' -> 1234.5 ; '' / '-' / None -> None"""
    if x is None:
        return None
    s = str(x).strip().replace(" ", "")
    if s in {"", "-", "--", "N/D", "ND", "s/d", "S/D"}:
        return None
    s = s.replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


# --------------------------------------------------------------------------------------
# Fechas en español -> ISO (YYYY-MM-DD)
# --------------------------------------------------------------------------------------

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def fecha_es_a_iso(texto: str) -> str | None:
    """Acepta:
    - 'Lunes, 24 de agosto del 2026'  /  '7 de septiembre 2026'
    - '09/09/2026'  /  '2026-09-09'
    Devuelve 'YYYY-MM-DD' o None.
    """
    if not texto:
        return None
    t = normaliza_texto(texto)

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return m.group(0)

    m = re.search(r"(\d{1,2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{4})", t)
    if m:
        d, mth, y = map(int, m.groups())
        try:
            return date(y, mth, d).isoformat()
        except ValueError:
            return None

    m = re.search(r"(\d{1,2})\s+de\s+([a-z]+)\s+(?:de[l]?\s+)?(\d{4})", t)
    if m:
        d = int(m.group(1))
        mth = _MESES.get(m.group(2))
        y = int(m.group(3))
        if mth:
            try:
                return date(y, mth, d).isoformat()
            except ValueError:
                return None
    return None


# --------------------------------------------------------------------------------------
# Unidades de venta -> libras (para poder comparar precios entre países)
# --------------------------------------------------------------------------------------

# Unidades "desnudas" con peso conocido. El resto se intenta leer del paréntesis.
_UNIDAD_LB = {
    "quintal": 100.0,
    "qq": 100.0,
    "arroba": 25.0,
    "@": 25.0,
    "libra": 1.0,
    "lb": 1.0,
    "onza": 1.0 / 16.0,
    "kilogramo": 2.20462,
    "kilo": 2.20462,
    "kg": 2.20462,
    "gramo": 2.20462 / 1000.0,
    "tonelada": 2204.62,
    "carga": 200.0,   # Honduras: carga = 200 lb (validado en reportes SIMPAH)
}

_TIPOS_UNIDAD = [
    "quintal", "arroba", "libra", "onza", "kilogramo", "kilo", "gramo", "tonelada",
    "carga", "caja", "cajilla", "saco", "costal", "bulto", "matate", "maleta",
    "canasto", "canasta", "cesta", "bolsa", "mazo", "mano", "docena", "media docena",
    "ciento", "cien", "unidad", "und", "litro", "galon", "envase", "bandeja", "red",
    "malla", "atado", "manojo", "trenza", "mecate",
]


def _lb_desde_parentesis(texto: str) -> float | None:
    """'Cien und (70-80 lb)' -> 75.0 ; 'Caja de cartón (5 kg)' -> 11.02 ;
    'Saco (50 lb)' -> 50.0 ; 'Mazo (30-40 g)' -> 0.077
    """
    t = normaliza_texto(texto)
    # todos los grupos "(numero[-numero] unidad)"
    for m in re.finditer(r"\(?\s*(\d+(?:\.\d+)?)\s*(?:[-a]\s*(\d+(?:\.\d+)?))?\s*(lb|kg|g|oz|libras?|kilos?|gramos?|onzas?)\b", t):
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else a
        val = (a + b) / 2.0
        u = m.group(3)
        if u.startswith("lb") or u.startswith("libra"):
            return val
        if u.startswith("kg") or u.startswith("kilo"):
            return val * 2.20462
        if u == "g" or u.startswith("gramo"):
            return val * 2.20462 / 1000.0
        if u.startswith("oz") or u.startswith("onza"):
            return val / 16.0
    return None


def unidad_a_libras(unidad_venta: str | None) -> tuple[str | None, float | None]:
    """Devuelve (unidad_tipo, cantidad_lb).

    unidad_tipo: palabra clave normalizada ('quintal', 'caja', 'libra'...).
    cantidad_lb: libras que contiene esa unidad, o None si no se puede saber
                 sin ambigüedad (p.ej. 'Docena' sin peso, 'Ciento' sin peso).
    """
    if not unidad_venta:
        return None, None
    t = normaliza_texto(unidad_venta)

    tipo = None
    for cand in _TIPOS_UNIDAD:
        if re.search(rf"\b{re.escape(cand)}\b", t):
            tipo = "cien" if cand == "cien" else cand
            break

    # 1) peso explícito en el texto
    lb = _lb_desde_parentesis(unidad_venta)
    if lb is not None:
        return tipo, round(lb, 4)

    # 2) unidad desnuda con peso conocido
    for k, v in _UNIDAD_LB.items():
        if re.search(rf"\b{re.escape(k)}\b", t):
            return (tipo or k), v

    return tipo, None


# --------------------------------------------------------------------------------------
# Clasificación de categoría por nombre de producto
# --------------------------------------------------------------------------------------

_CATS = {
    "granos": [
        "arroz", "frijol", "frijoles", "maiz", "sorgo", "soya", "soja", "trigo",
        "haba", "cafe", "cacao", "ajonjoli", "mani", "cebada", "avena", "lenteja",
        "garbanzo", "arveja", "semilla de jicaro", "semilla jicaro",
    ],
    "hortalizas": [
        "tomate", "miltomate", "tomatillo", "fresadilla", "cebolla", "cebollin",
        "chile", "chiltoma", "papa", "papas", "zanahoria",
        "repollo", "lechuga", "brocoli", "coliflor", "pepino", "ayote", "guicoy",
        "guisquil", "chayote", "yuca", "camote", "remolacha", "rabano", "apio",
        "culantro", "cilantro", "perejil", "espinaca", "acelga", "berro", "beterraga",
        "ejote", "habichuela", "vainica", "arveja china", "pataste", "guiquil",
        "malanga", "quequisque", "elote", "jilote", "loroco", "hierbabuena",
        "hierba buena", "yerbabuena", "ajo", "puerro", "pipian", "berenjena",
        "guicoy", "chilacayote", "chilote", "perulero", "guisquil", "guiquil",
        "papaya verde", "platano verde",
    ],
    "frutas": [
        "aguacate", "banano", "platano", "guineo", "pina", "sandia", "melon",
        "papaya", "naranja", "mandarina", "limon", "mango", "manzana", "uva",
        "pera", "durazno", "fresa", "mora", "coco", "maracuya", "granadilla",
        "guayaba", "zapote", "mamey", "jocote", "nispero", "tamarindo", "nance",
        "marañon", "maranon", "caimito", "anona", "melocoton", "kiwi", "ciruela",
        "toronja", "pitahaya", "mandarina", "guanabana", "membrillo", "rambutan",
        "mangostan", "litchi", "arandano", "frambuesa", "grosella", "higo",
    ],
    "carnes": [
        "pollo", "res", "bovino", "cerdo", "porcino", "carne", "posta", "pechuga",
        "muslo", "pierna", "costilla", "chuleta", "molida", "higado", "menudos",
        "pavo", "chorizo", "longaniza", "canal", "vacuno", "hueso",
    ],
    "lacteos": [
        "leche", "queso", "crema", "mantequilla", "cuajada", "requeson", "yogur",
        "yogurt", "quesillo",
    ],
    "huevos": ["huevo", "huevos", "cajilla"],
    "pesca": [
        "pescado", "pez", "filete", "tilapia", "mojarra", "corvina", "robalo",
        "roncador", "dorado", "pargo", "camaron", "langosta", "jaiba", "mariscos",
        "bagre", "juilin", "macarela", "atun", "sardina", "calamar", "pulpo",
        "tiburon", "cazon", "ostra", "almeja", "concha", "guapote", "runcador",
    ],
    "abarrotes": [
        "aceite", "azucar", "sal", "harina", "pan", "pasta", "fideo", "cafe molido",
        "manteca",
    ],
}


# pista de la fuente (subcategoría de la imagen NI, o categoría del bloque) -> categoría
_PISTA_MAP = {
    "carnes": "carnes", "carne": "carnes", "pecuarios": "carnes", "pecuario": "carnes",
    "lacteos": "lacteos", "lacteo": "lacteos",
    "mariscos": "pesca", "marisco": "pesca", "pesca": "pesca", "pescados": "pesca",
    "granos": "granos", "grano": "granos", "granos basicos": "granos",
    "hortalizas": "hortalizas", "hortaliza": "hortalizas", "verduras": "hortalizas",
    "frutas": "frutas", "fruta": "frutas",
    "huevos": "huevos", "huevo": "huevos",
}


def clasifica_categoria(producto: str | None, pista: str | None = None) -> str:
    """1) match por nombre de producto con LÍMITE DE PALABRA (evita que 'res' de
    'carnes' pegue dentro de 'fresco'). 2) si nada pega, usa la pista de la fuente.
    """
    p = normaliza_texto(producto)
    for cat, palabras in _CATS.items():
        for w in palabras:
            if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", p):
                return cat
    if pista:
        pn = normaliza_texto(pista)
        if pn in _PISTA_MAP:
            return _PISTA_MAP[pn]
        for k, v in _PISTA_MAP.items():
            if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", pn):
                return v
    return "otros"


# --------------------------------------------------------------------------------------
# Registro canónico
# --------------------------------------------------------------------------------------

# columnas de la tabla `registros` (orden estable para el CSV)
COLUMNAS = [
    "pais", "fecha", "fuente", "mercado", "ciudad", "segmento", "categoria",
    "subcategoria", "producto", "producto_norm", "variedad", "calidad", "tamano",
    "origen", "unidad_venta", "unidad_tipo", "cantidad_lb", "moneda",
    "precio_min", "precio_max", "precio_moda", "precio_prom", "precio_ref",
    "precio_lb_local", "tc_usd", "precio_ref_usd", "precio_lb_usd",
    "url_fuente", "reporte_id", "hash", "capturado_en",
]


def _hash(r: dict) -> str:
    clave = "|".join(normaliza_texto(str(r.get(k, ""))) for k in (
        "pais", "fecha", "segmento", "mercado", "producto", "tamano",
        "origen", "unidad_venta",
    ))
    return hashlib.sha1(clave.encode("utf-8")).hexdigest()[:16]


def construye_registro(**kw) -> dict:
    """Rellena derivados (precio_ref, cantidad_lb, categoria, hash...) a partir de
    los campos crudos que entrega cada extractor. No toca USD (eso lo hace fx.py).
    """
    r = {c: kw.get(c) for c in COLUMNAS}

    r["producto"] = limpia_espacios(r["producto"])
    r["mercado"] = limpia_espacios(r["mercado"])
    r["unidad_venta"] = limpia_espacios(r["unidad_venta"])
    r["origen"] = limpia_espacios(r["origen"])
    r["tamano"] = limpia_espacios(r["tamano"])
    r["producto_norm"] = normaliza_texto(r["producto"])

    for k in ("precio_min", "precio_max", "precio_moda", "precio_prom"):
        r[k] = parse_numero(r[k])

    # precio representativo: moda -> promedio -> punto medio del rango -> único valor
    ref = r["precio_moda"]
    if ref is None:
        ref = r["precio_prom"]
    if ref is None and r["precio_min"] is not None and r["precio_max"] is not None:
        ref = (r["precio_min"] + r["precio_max"]) / 2.0
    if ref is None:
        ref = r["precio_min"] if r["precio_min"] is not None else r["precio_max"]
    r["precio_ref"] = round(ref, 4) if ref is not None else None

    if not r.get("categoria"):
        r["categoria"] = clasifica_categoria(r["producto"], kw.get("_pista_categoria"))

    tipo, lb = unidad_a_libras(r["unidad_venta"])
    r["unidad_tipo"] = r.get("unidad_tipo") or tipo
    r["cantidad_lb"] = lb
    if r["precio_ref"] is not None and lb:
        r["precio_lb_local"] = round(r["precio_ref"] / lb, 4)

    r["capturado_en"] = datetime.now().isoformat(timespec="seconds")
    r["hash"] = _hash(r)
    return r


def valida_registro(r: dict) -> list[str]:
    """Devuelve lista de problemas (vacía = ok)."""
    errs = []
    if not r.get("producto"):
        errs.append("sin producto")
    if not r.get("fecha") or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(r.get("fecha", ""))):
        errs.append(f"fecha inválida: {r.get('fecha')!r}")
    if r.get("precio_ref") is None:
        errs.append("sin precio")
    elif r["precio_ref"] <= 0 or r["precio_ref"] > 5_000_000:
        errs.append(f"precio fuera de rango: {r['precio_ref']}")
    if r.get("pais") not in {"Guatemala", "Honduras", "Nicaragua"}:
        errs.append(f"país inválido: {r.get('pais')!r}")
    return errs
