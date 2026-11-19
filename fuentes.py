"""Lectores de cada web. Cada función devuelve una lista de pisos con el mismo formato:

{fuente, id, url, titulo, descripcion, precio, metros, habitaciones, municipio, barrio,
 lat, lon, particular (True/False/None), anunciante, telefono, email, fotos [urls],
 temporada (bool), extras {mascotas, aire, calefaccion, terraza, parking, ascensor},
 es_habitacion (bool), referencia}
"""
import html as html_lib
import json
import re
import time
import urllib.request

import config

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def descargar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def _props_json(h):
    """Saca el JSON de window.__INITIAL_PROPS__ (Habitaclia, Fotocasa, Milanuncios)."""
    m = re.search(r'window\.__INITIAL_PROPS__ = JSON\.parse\((".*?")\);', h, re.S)
    if m:
        return json.loads(json.loads(m.group(1)))
    m = re.search(r'<script[^>]*id="__initial_props__"[^>]*>(.*?)</script>', h, re.S)
    if m:
        return json.loads(m.group(1))
    return None


def _piso(**kw):
    base = {"fuente": "", "id": "", "url": "", "titulo": "", "descripcion": "", "precio": None,
            "metros": None, "habitaciones": None, "municipio": "", "barrio": "", "lat": None,
            "lon": None, "particular": None, "anunciante": "", "telefono": "", "email": "",
            "fotos": [], "temporada": False, "es_habitacion": False, "referencia": "",
            "extras": {}}
    base.update(kw)
    # Algunos portales mandan los acentos codificados ("Vall&#xE8;s"); los
    # decodificamos aquí para que todos los textos salgan bien y la zona se reconozca.
    for campo in ("titulo", "descripcion", "municipio", "barrio", "anunciante"):
        if isinstance(base[campo], str):
            base[campo] = html_lib.unescape(base[campo]).strip()
    return base


# --------------------------------------------------------------------------- Habitaclia
def habitaclia():
    pisos, pagina, paginas = [], 1, 1
    while pagina <= paginas:
        # la página va en la ruta (/s/2); con ?page=2 la web devuelve siempre la primera
        url = (f"https://www.habitaclia.com/alquiler/viviendas/barcelona-provincia/s"
               + (f"/{pagina}" if pagina > 1 else "") + f"?maxPrice={config.PRECIO_MAXIMO}")
        d = _props_json(descargar(url))
        ctx = d["initialSearchResultsPage"]["initialSearchContext"]
        paginas = min(ctx["results"]["pagination"]["totalPages"], 15)
        for it in ctx["results"]["items"]:
            s, p, t = it["summary"], it["property"], it["transaction"]
            loc = s.get("location") or {}
            coords = loc.get("coordinates") or {}
            pub = s.get("publisher") or {}
            feats = (p.get("features") or {})
            tiene, no_tiene = set(feats.get("has") or []), set(feats.get("hasNot") or [])
            texto = (s.get("title") or "") + " " + (s.get("description") or "")
            pisos.append(_piso(
                fuente="habitaclia", id=it["id"],
                url="https://www.habitaclia.com" + it["navigationUrl"],
                titulo=s.get("title") or "", descripcion=s.get("description") or "",
                precio=(t.get("price") or {}).get("amount"),
                metros=p.get("builtSurface"), habitaciones=p.get("rooms"),
                municipio=loc.get("municipality") or "", barrio=loc.get("district") or "",
                lat=coords.get("latitude"), lon=coords.get("longitude"),
                particular=pub.get("isPrivate"), anunciante=pub.get("tradeName") or pub.get("name") or "",
                telefono=(it.get("contact") or {}).get("phone") or "",
                email=(it.get("contact") or {}).get("email") or "",
                fotos=[i["url"] for i in (s.get("multimedia") or {}).get("images", [])[:3]],
                temporada=bool(re.search(r"temporada|temporal", texto, re.I)),
                referencia=it.get("reference") or "",
                extras={
                    "mascotas": True if "PETS_ALLOWED" in tiene else None,
                    "aire": "AIR_CONDITIONER" in tiene,
                    "calefaccion": "HEATING" in tiene or bool(re.search(r"calefacci", texto, re.I)),
                    "terraza": bool((p.get("terrace") or {}).get("has")) or "BALCONY" in tiene,
                    "parking": "PRIVATE_PARKING" in tiene,
                    "ascensor": "ELEVATOR" in tiene,
                },
            ))
        pagina += 1
        time.sleep(config.PAUSA_ENTRE_PAGINAS)
    return pisos


# --------------------------------------------------------------------------- Fotocasa
def fotocasa(paginas=3):
    pisos = []
    for pagina in range(1, paginas + 1):
        sufijo = f"/{pagina}" if pagina > 1 else ""
        url = (f"https://www.fotocasa.es/es/alquiler/viviendas/barcelona-provincia/todas-las-zonas/l{sufijo}"
               f"?maxPrice={config.PRECIO_MAXIMO}&sortType=publicationDate")
        d = _props_json(descargar(url))
        items = d["initialSearch"]["result"]["realEstates"]
        for r in items:
            feats = {f["key"]: f["value"] for f in r.get("features") or []}
            dyn = set(r.get("dynamicFeatures") or [])
            ad = r.get("address") or {}
            coords = r.get("coordinates") or {}
            texto = r.get("description") or ""
            precio = r.get("rawPrice")
            if precio is None:
                m = re.search(r"[\d.]+", str(r.get("price") or ""))
                precio = int(m.group(0).replace(".", "")) if m else None
            detalle = (r.get("detail") or {}).get("es-ES") or ""
            pisos.append(_piso(
                fuente="fotocasa", id=str(r["id"]), url="https://www.fotocasa.es" + detalle,
                titulo=f"{r.get('buildingType', '')} en {r.get('location', '')}",
                descripcion=texto, precio=precio,
                metros=feats.get("surface"), habitaciones=feats.get("rooms"),
                municipio=ad.get("municipality") or ad.get("city") or "",
                barrio=ad.get("neighborhood") or ad.get("district") or "",
                lat=coords.get("latitude"), lon=coords.get("longitude"),
                particular=(r.get("clientType") in ("particular", "private")) if r.get("clientType") else None,
                anunciante=r.get("clientAlias") or "",
                telefono=r.get("phone") or "",
                fotos=[m["src"] for m in (r.get("multimedia") or []) if m.get("type") == "image"][:3],
                temporada=bool(r.get("isTemporaryRental")) or "IS_TEMPORARY" in dyn,
                es_habitacion="IS_SHARED" in dyn,
                extras={
                    "mascotas": True if "pets_allowed" in feats or "mascotas" in detalle else None,
                    "aire": "air_conditioner" in feats,
                    "calefaccion": "heating" in feats,
                    "terraza": "terrace" in feats or "balcony" in feats,
                    "parking": "parking" in feats,
                    "ascensor": "elevator" in feats,
                },
            ))
        time.sleep(config.PAUSA_ENTRE_PAGINAS)
    return pisos


# --------------------------------------------------------------------------- Milanuncios
def milanuncios(paginas=2):
    pisos = []
    for pagina in range(1, paginas + 1):
        url = (f"https://www.milanuncios.com/alquiler-de-pisos-en-barcelona/"
               f"?desde={config.PRECIO_MINIMO}&hasta={config.PRECIO_MAXIMO}"
               + (f"&pagina={pagina}" if pagina > 1 else ""))
        d = _props_json(descargar(url))
        for a in d["adListPagination"]["adList"]["ads"]:
            tags = {t["type"]: t["text"] for t in a.get("tags") or []}
            num = lambda s: int(re.search(r"\d+", s).group(0)) if s and re.search(r"\d+", s) else None
            imgs = []
            for i in a.get("images") or []:
                u = i.get("src") or i.get("url") if isinstance(i, dict) else i
                if u:
                    imgs.append(u if u.startswith("http") else "https://" + u)
            texto = (a.get("title") or "") + " " + (a.get("description") or "")
            pisos.append(_piso(
                fuente="milanuncios", id=str(a["id"]), url="https://www.milanuncios.com" + a["url"],
                titulo=a.get("title") or "", descripcion=a.get("description") or "",
                precio=((a.get("price") or {}).get("cashPrice") or {}).get("value"),
                metros=num(tags.get("metros cuadrados")), habitaciones=num(tags.get("dormitorios")),
                municipio=((a.get("city") or {}).get("name") or "").split("/")[0],
                particular=(a.get("sellerType") == "private"),
                anunciante=a.get("seoTitle") or "", fotos=imgs[:3],
                temporada=bool(re.search(r"temporada|temporal", texto, re.I)),
                es_habitacion=bool(re.search(r"\bhabitaci[oó]n\b", a.get("title") or "", re.I)),
            ))
        time.sleep(config.PAUSA_ENTRE_PAGINAS)
    return pisos


# --------------------------------------------------------------------------- pisos.com
def pisoscom(paginas=3):
    pisos = []
    for pagina in range(1, paginas + 1):
        sufijo = f"{pagina}/" if pagina > 1 else ""
        url = f"https://www.pisos.com/alquiler/pisos-barcelona/hasta-{config.PRECIO_MAXIMO}/fecharecientedesde-desc/{sufijo}"
        h = descargar(url)
        bloques = re.split(r'<div id="(?=[\d.]+" class="ad-preview)', h)[1:]
        for b in bloques:
            ad_id = b.split('"', 1)[0]
            ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', b, re.S)
            info = {}
            if ld:
                try:
                    info = json.loads(ld.group(1))
                except ValueError:
                    info = {}
            precio = re.search(r'data-ad-price="(\d+)"', b)
            limpio = re.sub(r"<script.*?</script>", "", b, flags=re.S)
            chars = [html_lib.unescape(re.sub(r"\s+", " ", c)).strip()
                     for c in re.findall(r'class="ad-preview__char[^"]*">(.*?)</', limpio, re.S)]
            hab = next((int(re.search(r"\d+", c).group(0)) for c in chars if "hab" in c and re.search(r"\d+", c)), None)
            m2 = next((int(re.search(r"\d+", c).group(0)) for c in chars if "m²" in c and re.search(r"\d+", c)), None)
            desc = re.search(r'class="ad-preview__description[^"]*">(.*?)</', limpio, re.S)
            desc = html_lib.unescape(desc.group(1)).strip() if desc else ""
            sub = re.search(r'class="p-sm ad-preview__subtitle[^"]*">(.*?)</', limpio, re.S)
            titulo = html_lib.unescape(info.get("name") or "")
            geo = info.get("geo") or {}
            muni = ((info.get("address") or {}).get("addressLocality") or "").replace(" Capital", "")
            texto = titulo + " " + desc
            agencia = re.search(r'/inmobiliaria-([a-z0-9_]+?)(?:_\d+(?:_\d+)?)?/', b)
            pisos.append(_piso(
                fuente="pisoscom", id=ad_id, url="https://www.pisos.com" + (info.get("url") or ""),
                titulo=titulo, descripcion=desc, precio=int(precio.group(1)) if precio else None,
                metros=m2, habitaciones=hab, municipio=muni,
                barrio=html_lib.unescape(sub.group(1)).strip() if sub else "",
                lat=float(geo["latitude"]) if geo.get("latitude") else None,
                lon=float(geo["longitude"]) if geo.get("longitude") else None,
                particular=agencia is None,
                anunciante=agencia.group(1).replace("_", " ") if agencia else "",
                fotos=[info["image"]] if info.get("image") else [],
                temporada=bool(re.search(r"temporada|temporal", texto, re.I)),
                es_habitacion=bool(re.search(r"\bhabitaci[oó]n\b", titulo, re.I)),
            ))
        time.sleep(config.PAUSA_ENTRE_PAGINAS)
    return pisos


TODAS = {"habitaclia": habitaclia, "fotocasa": fotocasa, "milanuncios": milanuncios, "pisoscom": pisoscom}
