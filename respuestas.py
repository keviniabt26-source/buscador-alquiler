"""Lee la bandeja del Gmail del robot y reenvía al grupo de SEGUIMIENTO las respuestas nuevas
de agencias y propietarios.

- No marca los correos como leídos: en Gmail seguiréis viéndolos como nuevos.
- Recuerda qué correos ya ha reenviado (solo una huella, nunca el contenido ni la dirección).
- Si el remitente es alguien a quien el robot escribió, indica de qué piso se trata.

Necesita: GMAIL_USUARIO, GMAIL_CLAVE_APP, TELEGRAM_TOKEN, TELEGRAM_SEGUIMIENTO_ID
"""
import email
import hashlib
import hmac
import html
import imaplib
import os
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr

import avisos

IGNORAR = ("no-reply@accounts.google.com", "noreply@google.com", "googlecommunityteam-noreply@google.com")


def huella(texto):
    """Huella con clave secreta: permite reconocer un correo/dirección sin guardarlo legible."""
    clave = os.environ.get("SAL_TELEFONOS", "sin-clave").encode()
    return hmac.new(clave, (texto or "").strip().lower().encode(), hashlib.sha256).hexdigest()[:16]


def _decodificar(valor):
    try:
        return str(make_header(decode_header(valor or "")))
    except Exception:
        return valor or ""


def _texto_plano(msg):
    """Saca el texto del correo y quita la parte citada (nuestro mensaje original)."""
    cuerpo = ""
    partes = msg.walk() if msg.is_multipart() else [msg]
    for parte in partes:
        if parte.get_content_type() == "text/plain" and "attachment" not in str(parte.get("Content-Disposition", "")):
            cuerpo = parte.get_payload(decode=True).decode(parte.get_content_charset() or "utf-8", "ignore")
            break
    if not cuerpo:
        for parte in partes:
            if parte.get_content_type() == "text/html":
                h = parte.get_payload(decode=True).decode(parte.get_content_charset() or "utf-8", "ignore")
                cuerpo = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?i)<br\s*/?>|</p>", "\n", h)))
                break
    lineas = []
    for ln in cuerpo.splitlines():
        if ln.strip().startswith(">"):
            continue
        if re.match(r"^\s*(El .+ escribió:|On .+ wrote:|-----\s*Original|De: |From: )", ln):
            break  # a partir de aquí suele venir nuestro correo citado
        lineas.append(ln.rstrip())
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
    return texto[:900] + ("…" if len(texto) > 900 else "")


def revisar(estado):
    usuario, clave = os.environ.get("GMAIL_USUARIO"), os.environ.get("GMAIL_CLAVE_APP")
    chat = os.environ.get("TELEGRAM_SEGUIMIENTO_ID")
    if not (usuario and clave and chat):
        print("  (lectura de respuestas sin configurar)")
        return
    vistas = set(estado.get("respuestas_vistas", []))
    contactados = {c["destino"]: c for c in estado.get("contactados", [])}
    desde = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
    m = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
    try:
        m.login(usuario, clave)
        m.select("INBOX", readonly=True)  # readonly: no se marcan como leídos
        _, datos = m.search(None, f'(SINCE "{desde}")')
        nuevos = 0
        for num in datos[0].split():
            _, partes = m.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(partes[0][1])
            mid = huella(msg.get("Message-ID") or (msg.get("Date", "") + msg.get("From", "")))
            if mid in vistas:
                continue
            vistas.add(mid)
            nombre, direccion = parseaddr(_decodificar(msg.get("From")))
            d = direccion.lower()
            if d == usuario.lower() or d in IGNORAR or re.search(r"@([a-z0-9-]+\.)*google\.com$", d) \
                    or (re.search(r"no-?reply|donotreply", d) and "mailer-daemon" not in d):
                continue  # correos de Google, avisos automáticos y nuestros propios envíos
            asunto = _decodificar(msg.get("Subject"))
            rebote = "mailer-daemon" in direccion.lower() or "delivery status" in asunto.lower()
            piso = contactados.get(huella(direccion))
            if rebote:
                cab = "⚠️ <b>Correo NO entregado</b> (dirección que no funciona)"
            else:
                cab = f"📩 <b>Respuesta de {html.escape(nombre or direccion)}</b>"
            lineas = [cab]
            if piso:
                lineas.append(f"Sobre el piso de <b>{html.escape(piso['municipio'])}</b> · {piso['precio']} € · "
                              f'<a href="{html.escape(piso["url"], quote=True)}">ver anuncio</a>')
            lineas.append(f"Asunto: {html.escape(asunto)}")
            if not rebote:
                lineas.append(f"✉️ {html.escape(direccion)}")
                lineas.append("\n" + html.escape(_texto_plano(msg) or "(sin texto)"))
            lineas.append("\n👉 Contestad desde el Gmail del robot o llamadles.")
            avisos.mensaje_html("\n".join(lineas), chats=[chat])
            nuevos += 1
        print(f"Respuestas nuevas reenviadas: {nuevos}")
    finally:
        try:
            m.logout()
        except Exception:
            pass
    estado["respuestas_vistas"] = sorted(vistas)[-3000:]
