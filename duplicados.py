"""Detecta si un piso es el mismo que otro ya visto (aunque esté en otro portal).

Pistas, de más fuerte a más débil:
  1. Misma foto (huella de imagen "dHash": sale casi igual aunque la recorten o cambien de tamaño)
  2. Mismo teléfono y precio parecido
  3. Mismo municipio + precio parecido + mismos metros (±3) + mismas habitaciones
No usa ninguna IA de pago: todo son reglas.
"""
import hashlib
import hmac
import io
import os
import re
import urllib.request

from clasificar import normalizar

try:
    from PIL import Image
except ImportError:  # sin Pillow funciona igual, solo pierde la pista de las fotos
    Image = None

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"


def huella_foto(url):
    if not Image or not url:
        return None
    try:
        u = url.replace("rule=original", "rule=web_370x277_ar")
        req = urllib.request.Request(u, headers={"User-Agent": UA})
        datos = urllib.request.urlopen(req, timeout=15).read()
        img = Image.open(io.BytesIO(datos)).convert("L").resize((9, 8))
        px = list(img.getdata())
        bits = 0
        for fila in range(8):
            for col in range(8):
                bits = (bits << 1) | (px[fila * 9 + col] > px[fila * 9 + col + 1])
        return f"{bits:016x}"
    except Exception:
        return None


def distancia(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def huella_telefono(tel):
    """No guardamos el teléfono (el proyecto es público): guardamos una huella con clave secreta.
    El mismo número siempre da la misma huella, pero sin la clave no se puede volver al número."""
    d = re.sub(r"\D", "", tel or "")
    sal = os.environ.get("SAL_TELEFONOS", "")
    if len(d) < 9 or not sal:
        return ""
    return hmac.new(sal.encode(), d[-9:].encode(), hashlib.sha256).hexdigest()[:16]


def ficha(p):
    """Lo que guardamos de cada piso para poder compararlo después."""
    return {
        "clave": f"{p['fuente']}:{p['id']}",
        "municipio": normalizar(p["municipio"]),
        "precio": p["precio"],
        "metros": p["metros"],
        "barrio": normalizar(p.get("barrio") or ""),
        "habitaciones": p["habitaciones"],
        "telefono": huella_telefono(p["telefono"]),
        "fotos": [h for h in (p.get("_huellas") or []) if h],
        "particular": bool(p["particular"]),
        "url": p["url"],
    }


def precio_parecido(a, b):
    return a and b and abs(a - b) <= max(30, 0.05 * max(a, b))


def mismo_barrio(f, g):
    a, b = f.get("barrio", ""), g.get("barrio", "")
    return not a or not b or a == b


def quitar_fotos_genericas(pisos, genericas, maximo=3):
    """Logos de agencia o imágenes «sin foto» salen en muchos anuncios distintos:
    esas huellas no sirven para decir que dos pisos son el mismo, así que se descartan."""
    from collections import Counter
    cuenta = Counter(h for p in pisos for h in set(p.get("_huellas") or []) if h)
    genericas.update(h for h, n in cuenta.items() if n > maximo)  # se recuerdan para las siguientes veces
    for p in pisos:
        p["_huellas"] = [h for h in (p.get("_huellas") or []) if h and h not in genericas]


def buscar_igual(f, fichas):
    """Devuelve la ficha guardada que corresponde al mismo piso, o None.
    Mejor dejar pasar un repetido que perder un piso: las reglas son estrictas."""
    for g in fichas:
        if g["clave"] == f["clave"]:
            return g
        if f["fotos"] and g["fotos"] and any(distancia(a, b) <= 6 for a in f["fotos"] for b in g["fotos"]):
            return g
        mismos_datos = (f["municipio"] == g["municipio"] and f["metros"] and g["metros"]
                        and f["habitaciones"] is not None and f["habitaciones"] == g["habitaciones"])
        # Mismo contacto: una agencia tiene muchos pisos, así que además tienen que coincidir los datos
        if (f["telefono"] and f["telefono"] == g["telefono"] and mismos_datos
                and precio_parecido(f["precio"], g["precio"]) and abs(f["metros"] - g["metros"]) <= 5):
            return g
        # Sin contacto ni foto: casi idénticos (precio ±10 €, metros ±2, mismo barrio si se sabe)
        if (mismos_datos and f["precio"] and g["precio"] and abs(f["precio"] - g["precio"]) <= 10
                and abs(f["metros"] - g["metros"]) <= 2 and mismo_barrio(f, g)):
            return g
    return None
