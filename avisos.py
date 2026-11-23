"""Envía los avisos al móvil: Telegram (con foto y botón) y/o WhatsApp (solo texto, vía CallMeBot)."""
import html
import json
import os
import time
import urllib.parse
import urllib.request

import config


def texto_aviso(p, color, etiqueta, iconos, motivo_extra=""):
    lineas = [f"{color} <b>{html.escape(etiqueta)}</b>"]
    if motivo_extra:
        lineas.append(f"<b>{html.escape(motivo_extra)}</b>")
    zona = p["municipio"] + (f" ({p['barrio'].strip()})" if p["barrio"].strip() else "")
    datos = [f"<b>{p['precio']} €</b>"]
    if p["habitaciones"] is not None:
        datos.append(f"{p['habitaciones']} hab")
    if p["metros"]:
        datos.append(f"{p['metros']} m²")
    lineas.append(f"{html.escape(zona)} · " + " · ".join(datos))
    if iconos:
        lineas.append(" ".join(iconos))
    quien = p["anunciante"] or ("Particular" if p["particular"] else "")
    if quien:
        lineas.append(f"Anunciante: {html.escape(quien)}")
    if p["telefono"]:
        lineas.append(f"📞 {html.escape(p['telefono'])}")
    if p["email"]:
        lineas.append(f"✉️ {html.escape(p['email'])}")
    lineas.append(f"Fuente: {p['fuente']}")
    return "\n".join(lineas)


def _post(url, datos):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(datos).encode())
    return urllib.request.urlopen(req, timeout=20).read()


def _chats():
    return [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]


def movil_whatsapp(telefono):
    """Devuelve el móvil en formato internacional (34XXXXXXXXX) si es un móvil español; si no, None.
    Los fijos (9XX) no tienen WhatsApp, así que no se ofrece el botón."""
    cifras = "".join(c for c in (telefono or "") if c.isdigit())
    if cifras.startswith("0034"):
        cifras = cifras[4:]
    elif cifras.startswith("34") and len(cifras) == 11:
        cifras = cifras[2:]
    if len(cifras) == 9 and cifras[0] in "67":
        return "34" + cifras
    return None


def enlace_whatsapp(p):
    """Botón de WhatsApp con el mensaje ya escrito (solo particulares con móvil).
    Abre el WhatsApp de quien lo pulsa: el mensaje sale desde vuestro número y lo enviáis vosotros."""
    if not p.get("particular"):
        return None
    numero = movil_whatsapp(p.get("telefono"))
    if not numero:
        return None
    firma = os.environ.get("DATOS_FIRMA", "").strip()
    zona = p["municipio"] + (f" ({p['barrio'].strip()})" if (p.get("barrio") or "").strip() else "")
    texto = (f"Hola, buenos días. Hemos visto su anuncio del piso en {zona} por {p['precio']} €/mes "
             f"y nos interesa mucho. Somos una pareja con trabajos estables, contamos con avalista "
             f"familiar y tenemos toda la documentación preparada. ¿Sigue disponible? "
             f"Nos encantaría visitarlo cuando le vaya bien. Muchas gracias"
             + (f", {firma}." if firma else "."))
    return f"https://wa.me/{numero}?text=" + urllib.parse.quote(texto)


def telegram(texto_html, url_anuncio, foto=None, silencio=False, whatsapp=None):
    """Un piso = un mensaje con foto, datos y botón. silencio=True: llega sin sonido ni vibración.
    whatsapp: enlace wa.me con el mensaje preparado (se añade como segundo botón)."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chats = _chats()
    if not token or not chats:
        print("  (Telegram sin configurar)")
        return
    fila = [{"text": "🔗 Ver anuncio", "url": url_anuncio}]
    if whatsapp:
        fila.append({"text": "💬 WhatsApp al propietario", "url": whatsapp})
    botones = json.dumps({"inline_keyboard": [fila]})
    callado = "true" if silencio else "false"
    for chat in chats:
        try:
            if foto:
                _post(f"https://api.telegram.org/bot{token}/sendPhoto",
                      {"chat_id": chat, "photo": foto, "caption": texto_html[:1024],
                       "parse_mode": "HTML", "reply_markup": botones, "disable_notification": callado})
                continue
        except Exception as e:
            print("  foto no aceptada, envío solo texto:", e)
        _post(f"https://api.telegram.org/bot{token}/sendMessage",
              {"chat_id": chat, "text": texto_html, "parse_mode": "HTML", "reply_markup": botones,
               "disable_web_page_preview": "false", "disable_notification": callado})


def linea_lista(p):
    """Una línea corta para las listas: precio · pueblo · m² · hab · enlace."""
    zona = p["municipio"] + (f" ({p['barrio'].strip()})" if (p.get("barrio") or "").strip() else "")
    trozos = [f"<b>{p['precio']} €</b>", html.escape(zona)]
    if p.get("metros"):
        trozos.append(f"{p['metros']} m²")
    if p.get("habitaciones") is not None:
        trozos.append(f"{p['habitaciones']} hab")
    if p.get("particular"):
        trozos.append("👤")
    linea = (p.get("color") or "•") + " " + " · ".join(trozos) + f' · <a href="{html.escape(p["url"], quote=True)}">ver</a>'
    if p.get("motivo"):
        linea += f" ({html.escape(p['motivo'])})"
    return linea


def lista(titulo, pisos, silencio=True):
    """Manda una lista de pisos en uno o varios mensajes (Telegram admite ~4000 caracteres por mensaje)."""
    if not pisos:
        return
    lineas = [linea_lista(p) for p in pisos]
    bloques, actual = [], ""
    for ln in lineas:
        if len(actual) + len(ln) + 1 > 3800:
            bloques.append(actual)
            actual = ""
        actual += ln + "\n"
    bloques.append(actual)
    for i, b in enumerate(bloques):
        cabecera = f"<b>{html.escape(titulo)}</b>" + (f" ({i + 1}/{len(bloques)})" if len(bloques) > 1 else "")
        mensaje_html(cabecera + "\n\n" + b, silencio=silencio)
        time.sleep(1)


def mensaje_html(texto_html, silencio=False, chats=None):
    """Mensaje con formato (negritas y enlaces). Devuelve los id de mensaje (para poder fijarlo).
    chats: lista de chats destino; por defecto, el grupo de pisos (TELEGRAM_CHAT_ID)."""
    token = os.environ.get("TELEGRAM_TOKEN")
    ids = []
    for chat in (chats or _chats()):
        r = json.loads(_post(f"https://api.telegram.org/bot{token}/sendMessage",
                             {"chat_id": chat, "text": texto_html, "parse_mode": "HTML",
                              "disable_web_page_preview": "true",
                              "disable_notification": "true" if silencio else "false"}))
        ids.append((chat, r["result"]["message_id"]))
    return ids


def fijar(ids):
    """Fija un mensaje arriba del chat (el bot tiene que ser administrador del grupo)."""
    token = os.environ.get("TELEGRAM_TOKEN")
    for chat, mid in ids:
        try:
            _post(f"https://api.telegram.org/bot{token}/pinChatMessage",
                  {"chat_id": chat, "message_id": mid, "disable_notification": "true"})
        except Exception as e:
            print("  no he podido fijar el mensaje:", e)


LEYENDA = """📌 <b>CÓMO FUNCIONA RASTREATOR</b>

Cada 15 minutos miro <b>Habitaclia, Fotocasa y pisos.com</b> y os aviso de los pisos <b>NUEVOS</b> de alquiler en toda la provincia de Barcelona que cumplen:
✔️ Máximo 1.000 €/mes · ✔️ Mínimo 30 m² · ✔️ Pisos, estudios y lofts (sin habitaciones sueltas)

<b>COLORES Y CÓMO OS LLEGAN</b>
🔴 <b>LLAMA YA</b> → zona cercana y además lo anuncia un particular o cuesta 800 € o menos. Llega al momento <b>con sonido</b>: ¡contactad rápido!
🟢 <b>INTERESANTE</b> → zona cercana (Vallès, BCN y alrededores), de agencia. Llega al momento <b>en silencio</b>.
🟡 <b>LEJOS</b> → fuera de la zona cercana. Van todos juntos en <b>un resumen al día a las 21:00</b>.

<b>AVISOS ESPECIALES</b>
💸 <b>HA BAJADO DE PRECIO</b> → un piso que ya os mandé ahora es más barato.
👤 <b>Ahora lo anuncia un PARTICULAR</b> → un piso que ya os mandé aparece también de particular.

<b>ICONOS</b>
👤 particular · 🐾 admite mascotas · 🚫🐾 no mascotas · ⚠️ alquiler de temporada
❄️ aire · 🔥 calefacción · 🌿 terraza/balcón · 🚗 parking · 🛗 ascensor

<b>CONTACTO AUTOMÁTICO (solo 🔴)</b>
✉️ <b>Ya les hemos escrito un correo</b> → el robot ha mandado vuestra presentación al anunciante.
⚠️ <b>Sin email</b> → no hay correo: llamad o rellenad el formulario del anuncio.
💬 <b>WhatsApp al propietario</b> → botón con el mensaje ya escrito (solo particulares con móvil): pulsad y enviad.
📩 Las <b>respuestas</b> de agencias y propietarios llegan al grupo <b>Seguimiento Pisos 🍀</b>.

<b>🔗 Ver anuncio</b> (o «ver» en las listas) → abre el piso en la web.

⚙️ Si alguna web deja de funcionar, os aviso una sola vez."""


def whatsapp(texto_html, url_anuncio):
    """CallMeBot: servicio gratuito que manda WhatsApp a TU propio número (solo texto)."""
    telefono, clave = os.environ.get("CALLMEBOT_PHONE"), os.environ.get("CALLMEBOT_APIKEY")
    if not telefono or not clave:
        print("  (WhatsApp sin configurar)")
        return
    plano = html.unescape(texto_html.replace("<b>", "*").replace("</b>", "*")) + f"\n{url_anuncio}"
    url = ("https://api.callmebot.com/whatsapp.php?" +
           urllib.parse.urlencode({"phone": telefono, "text": plano, "apikey": clave}))
    urllib.request.urlopen(url, timeout=30).read()


def avisar(texto_html, url_anuncio, foto=None, silencio=False, whatsapp=None):
    if config.CANAL_AVISOS in ("telegram", "ambos"):
        telegram(texto_html, url_anuncio, foto, silencio, whatsapp)
    if config.CANAL_AVISOS in ("whatsapp", "ambos"):
        whatsapp(texto_html, url_anuncio)


def mensaje_simple(texto):
    """Para avisos del propio robot (errores, resumen de la primera ejecución)."""
    if config.CANAL_AVISOS in ("telegram", "ambos"):
        token = os.environ.get("TELEGRAM_TOKEN")
        for chat in [c for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]:
            if token:
                _post(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat.strip(), "text": texto})
    if config.CANAL_AVISOS in ("whatsapp", "ambos") and os.environ.get("CALLMEBOT_APIKEY"):
        url = ("https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
            {"phone": os.environ["CALLMEBOT_PHONE"], "text": texto, "apikey": os.environ["CALLMEBOT_APIKEY"]}))
        urllib.request.urlopen(url, timeout=30).read()


def documento(ruta, texto=""):
    """Manda un archivo (p. ej. el CSV de la primera vez) al grupo de Telegram."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    if not token or not chats:
        print("  (Telegram sin configurar)")
        return
    nombre = os.path.basename(ruta)
    with open(ruta, "rb") as fh:
        contenido = fh.read()
    for chat in chats:
        limite = "----robotpisos7f3a"
        partes = []
        for k, v in {"chat_id": chat, "caption": texto[:1024]}.items():
            partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        partes.append((f'--{limite}\r\nContent-Disposition: form-data; name="document"; filename="{nombre}"\r\n'
                       f'Content-Type: text/csv\r\n\r\n').encode() + contenido + b"\r\n")
        partes.append(f"--{limite}--\r\n".encode())
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendDocument", data=b"".join(partes),
                                     headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
        urllib.request.urlopen(req, timeout=60).read()
