"""Envía los avisos al móvil: Telegram (con foto y botón) y/o WhatsApp (solo texto, vía CallMeBot)."""
import html
import json
import os
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


def telegram(texto_html, url_anuncio, foto=None):
    token = os.environ.get("TELEGRAM_TOKEN")
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    if not token or not chats:
        print("  (Telegram sin configurar)")
        return
    botones = json.dumps({"inline_keyboard": [[{"text": "🔗 Ver anuncio", "url": url_anuncio}]]})
    for chat in chats:
        try:
            if foto:
                _post(f"https://api.telegram.org/bot{token}/sendPhoto",
                      {"chat_id": chat, "photo": foto, "caption": texto_html[:1024],
                       "parse_mode": "HTML", "reply_markup": botones})
                continue
        except Exception as e:
            print("  foto no aceptada, envío solo texto:", e)
        _post(f"https://api.telegram.org/bot{token}/sendMessage",
              {"chat_id": chat, "text": texto_html, "parse_mode": "HTML", "reply_markup": botones,
               "disable_web_page_preview": "false"})


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


def avisar(texto_html, url_anuncio, foto=None):
    if config.CANAL_AVISOS in ("telegram", "ambos"):
        telegram(texto_html, url_anuncio, foto)
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
