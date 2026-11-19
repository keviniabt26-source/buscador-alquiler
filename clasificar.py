"""Decide si un piso pasa el filtro, qué nivel (color) tiene y qué iconos lleva."""
import re
import unicodedata

import config


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = t.replace(" capital", "").strip()
    # variantes en castellano que usan algunas webs
    equivalencias = {"san cugat del valles": "sant cugat del valles", "tarrasa": "terrassa",
                     "barbera del valles": "barbera del valles", "moncada y reixach": "montcada i reixac",
                     "hospitalet de llobregat": "l'hospitalet de llobregat",
                     "santa coloma de gramanet": "santa coloma de gramenet",
                     "cornella": "cornella de llobregat", "cerdanyola": "cerdanyola del valles"}
    return equivalencias.get(t, t)


CERCANA = {normalizar(m) for m in config.ZONA_CERCANA}

NO_MASCOTAS = re.compile(r"no (se )?(admiten|aceptan|permiten)( animales| mascotas)|sin (animales|mascotas)"
                         r"|no (animales|mascotas)|mascotas no", re.I)
SI_MASCOTAS = re.compile(r"(se )?(admiten|aceptan|permiten) (animales|mascotas)|mascotas (permitidas|bienvenidas)"
                         r"|pet ?friendly", re.I)


def pasa_filtro(p):
    """Devuelve (True, '') si pasa, o (False, motivo)."""
    if p["precio"] is None or p["precio"] < config.PRECIO_MINIMO:
        return False, "sin precio o precio absurdo"
    if p["precio"] > config.PRECIO_MAXIMO:
        return False, "caro"
    if p["metros"] and p["metros"] < config.METROS_MINIMOS:
        return False, "pequeño"
    if p["es_habitacion"] and not config.ACEPTAR_HABITACIONES:
        return False, "habitación"
    return True, ""


def es_cercana(p):
    return normalizar(p["municipio"]) in CERCANA


def mascotas(p):
    texto = f"{p['titulo']} {p['descripcion']}"
    if NO_MASCOTAS.search(texto):
        return False
    if p["extras"].get("mascotas") or SI_MASCOTAS.search(texto):
        return True
    return None


def nivel(p):
    if p["es_habitacion"]:
        return "🟣", "HABITACIÓN"
    cerca = es_cercana(p)
    if cerca and p["particular"]:
        return "🔴", "LLAMA YA – PARTICULAR"
    if cerca and p["precio"] <= config.PRECIO_GANGA:
        return "🔴", "LLAMA YA – BUEN PRECIO"
    if cerca:
        return "🟢", "INTERESANTE"
    return "🟡", "LEJOS – míralo cuando puedas"


def iconos(p):
    i = []
    m = mascotas(p)
    if m is True:
        i.append("🐾 admite mascotas")
    elif m is False:
        i.append("🚫🐾 no mascotas")
    if p["particular"]:
        i.append("👤 particular")
    if p["temporada"]:
        i.append("⚠️ temporada")
    e = p["extras"]
    for clave, icono in [("aire", "❄️ aire"), ("calefaccion", "🔥 calefacción"), ("terraza", "🌿 terraza/balcón"),
                         ("parking", "🚗 parking"), ("ascensor", "🛗 ascensor")]:
        if e.get(clave):
            i.append(icono)
    return i
