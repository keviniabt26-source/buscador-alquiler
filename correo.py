"""Envía el correo de "estamos interesados" desde la cuenta de Gmail configurada.

Necesita (en Secrets de GitHub o en .env):
  GMAIL_USUARIO        -> tu dirección de Gmail
  GMAIL_CLAVE_APP      -> "contraseña de aplicación" de Google (NO tu contraseña normal)
  DATOS_NOMBRES        -> p. ej. "Nombre y Nombre"
  DATOS_FIRMA          -> p. ej. "Nombre Apellido"
  DATOS_TELEFONO       -> tu móvil
  DATOS_TRABAJO_1/2    -> una línea por persona, p. ej. "Nombre: contrato indefinido en ... desde 20XX"
  ENLACE_PRESENTACION  -> enlace (Drive) a la presentación en PDF, SIN DNI ni nóminas
"""
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

PLANTILLA = Path(__file__).parent / "plantillas" / "correo_interes.txt"


def configurado():
    return all(os.environ.get(k) for k in ["GMAIL_USUARIO", "GMAIL_CLAVE_APP", "DATOS_NOMBRES",
                                           "DATOS_FIRMA", "DATOS_TELEFONO"])


def componer(p):
    texto = PLANTILLA.read_text(encoding="utf-8")
    asunto, cuerpo = texto.split("\n", 1)
    datos = {
        "municipio": p["municipio"],
        "precio": p["precio"],
        "referencia": f" (ref. {p['referencia']})" if p.get("referencia") else "",
        "url": p["url"],
        "nombres": os.environ.get("DATOS_NOMBRES", ""),
        "firma": os.environ.get("DATOS_FIRMA", ""),
        "telefono": os.environ.get("DATOS_TELEFONO", ""),
        "trabajo_1": os.environ.get("DATOS_TRABAJO_1", ""),
        "trabajo_2": os.environ.get("DATOS_TRABAJO_2", ""),
        "enlace_presentacion": os.environ.get("ENLACE_PRESENTACION", "(os la envío en cuanto me digáis)"),
    }
    return asunto.replace("ASUNTO:", "").strip().format(**datos), cuerpo.strip().format(**datos)


def enviar(p):
    asunto, cuerpo = componer(p)
    msg = EmailMessage()
    msg["From"] = os.environ["GMAIL_USUARIO"]
    msg["To"] = p["email"]
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(os.environ["GMAIL_USUARIO"], os.environ["GMAIL_CLAVE_APP"])
        s.send_message(msg)
