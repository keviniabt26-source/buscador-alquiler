"""ROBOT DE PISOS – programa principal.

Cada vez que se ejecuta:
  1. Lee los anuncios de todas las fuentes activas.
  2. Se queda con los que pasan el filtro (precio, metros, sin habitaciones…).
  3. Descarta los que ya conoce (aunque vengan de otro portal).
  4. Por cada piso NUEVO: lo clasifica (🔴🟢🟡), avisa al móvil y, si está activado,
     manda el correo de interés al anunciante.
  5. Guarda lo que ha visto en estado/estado.json.

Uso:
  python robot.py                     -> funcionamiento normal
  python robot.py --prueba            -> solo mira e imprime en pantalla; no avisa ni envía nada
  python robot.py --enviar-actuales   -> manda lo ya publicado (🔴 sueltos + listas 🟢/🟡), sin tocar la memoria
  python robot.py --enviar-actuales --muestra -> igual, pero solo una muestra pequeña (para revisar)
  python robot.py --leyenda           -> manda la leyenda y la fija arriba
"""
import html
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import avisos
import clasificar
import config
import correo
import duplicados
import fuentes
import respuestas

CARPETA = Path(__file__).parent
ESTADO = CARPETA / "estado" / "estado.json"
PRUEBA = "--prueba" in sys.argv
ACTUALES = "--enviar-actuales" in sys.argv   # manda los pisos ya publicados (🔴 sueltos + listas) sin tocar la memoria
MUESTRA = "--muestra" in sys.argv            # con --enviar-actuales: solo 2 🔴 y 8 por lista (para revisar)
LEYENDA = "--leyenda" in sys.argv            # manda la leyenda y la fija arriba del chat
MODO_INICIAL = False


def cargar_env():
    """En local, lee el archivo .env (en GitHub se usan los Secrets)."""
    env = CARPETA / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def cargar_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return {"fichas": [], "correos": {}, "errores_seguidos": {}, "primera_vez": True}


def guardar_estado(estado):
    ESTADO.parent.mkdir(exist_ok=True)
    # nos quedamos con los últimos 6000 pisos para que el archivo no crezca sin fin
    estado["fichas"] = estado["fichas"][-6000:]
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=0), encoding="utf-8")


def hoy():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")



def bloque_que_hacer(p, color, estado_correo):
    """Dos líneas claras al final de cada aviso 🔴/🟢: en qué punto estamos y qué tiene que hacer Kevin."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    hora = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%H:%M")
    hay_whatsapp = bool(avisos.enlace_whatsapp(p))
    contactar = ("pulsa «💬 WhatsApp al propietario» o llama" if hay_whatsapp
                 else "llama o rellena el formulario del anuncio")
    if estado_correo.startswith("✉️"):
        situacion = f"✉️ Ya les hemos escrito por correo (hoy a las {hora})"
        que_hacer = "Espera su respuesta (llega a Seguimiento 🍀). Si te urge, llama y diles que les escribisteis por email"
    elif estado_correo.startswith("ℹ️"):
        situacion = "ℹ️ Hoy ya les escribimos por otro piso"
        que_hacer = f"Si este también os interesa, {contactar} y nombrad este piso"
    elif estado_correo.startswith("⏳"):
        situacion = "❌ Nadie les ha escrito todavía (tope de correos de hoy)"
        que_hacer = contactar[0].upper() + contactar[1:]
    elif estado_correo.startswith("⚠️ No se pudo"):
        situacion = "❌ Falló el correo automático: nadie les ha escrito"
        que_hacer = contactar[0].upper() + contactar[1:]
    else:
        situacion = "❌ Nadie les ha escrito todavía" + (" (el anuncio no tiene email)" if estado_correo else "")
        que_hacer = ("Si os gusta: " + contactar) if color != "🔴" else contactar[0].upper() + contactar[1:]
    return (f"<b>📌 Situación:</b> {html.escape(situacion)}\n"
            f"<b>📄 Documentación:</b> no enviada (solo tras visitar, con tu ok)\n"
            f"<b>👉 Qué hacer:</b> {html.escape(que_hacer)}")

def main():
    global MODO_INICIAL
    cargar_env()
    if LEYENDA:
        avisos.fijar(avisos.mensaje_html(avisos.LEYENDA))
        print("Leyenda enviada y fijada")
        return
    estado = cargar_estado()
    primera_vez = estado.get("primera_vez", True)
    if ACTUALES:
        # empezamos con memoria vacía para tratar todo lo publicado como "nuevo",
        # pero conservamos las fotos genéricas que ya sabemos que hay que ignorar
        estado = {"fichas": [], "correos": {}, "errores_seguidos": {},
                  "fotos_genericas": estado.get("fotos_genericas", [])}
    MODO_INICIAL = ACTUALES or primera_vez

    # 1. Leer todas las fuentes (si una falla, las demás siguen)
    pisos = []
    for nombre in config.FUENTES_ACTIVAS:
        try:
            r = fuentes.TODAS[nombre]()
            print(f"{nombre}: {len(r)} anuncios leídos")
            pisos += r
            estado["errores_seguidos"][nombre] = 0
        except Exception as e:
            n = estado["errores_seguidos"].get(nombre, 0) + 1
            estado["errores_seguidos"][nombre] = n
            print(f"ERROR leyendo {nombre}: {e}")
            traceback.print_exc()
            if n == 6 and not PRUEBA:  # avisa una sola vez si una web falla seguido
                avisos.mensaje_simple(f"⚙️ El robot no consigue leer {nombre} desde hace un rato. Hay que revisarlo.")

    # 2. Filtro
    validos = []
    for p in pisos:
        ok, _ = clasificar.pasa_filtro(p)
        if ok:
            validos.append(p)
    print(f"Pasan el filtro: {len(validos)} de {len(pisos)}")

    # 3. Duplicados: primero lo barato (ya visto por su id), luego las huellas de foto
    vistas = {f["clave"] for f in estado["fichas"]}
    candidatos = [p for p in validos if f"{p['fuente']}:{p['id']}" not in vistas]
    with ThreadPoolExecutor(max_workers=8) as ex:
        huellas = list(ex.map(lambda p: [duplicados.huella_foto(u) for u in p["fotos"][:2]], candidatos))
    for p, h in zip(candidatos, huellas):
        p["_huellas"] = h
    genericas = set(estado.get("fotos_genericas", []))
    duplicados.quitar_fotos_genericas(candidatos, genericas)
    estado["fotos_genericas"] = sorted(genericas)

    nuevos, filas_csv = [], []
    for p in candidatos:
        f = duplicados.ficha(p)
        igual = duplicados.buscar_igual(f, estado["fichas"])
        estado["fichas"].append(f)
        if igual is None:
            nuevos.append((p, ""))
            continue
        # Es un piso repetido: solo avisamos si trae algo útil
        if p["precio"] and igual["precio"] and p["precio"] <= igual["precio"] - 20:
            nuevos.append((p, f"💸 HA BAJADO DE PRECIO: antes {igual['precio']} €"))
        elif p["particular"] and not igual["particular"]:
            nuevos.append((p, "👤 Ahora también lo anuncia un PARTICULAR"))

    print(f"Pisos nuevos de verdad: {len(nuevos)}")

    # 4. Avisar y escribir
    #    🔴 -> mensaje al momento CON sonido   🟢 -> mensaje al momento EN SILENCIO
    #    🟡 -> se guarda para el resumen diario (HORA_RESUMEN)
    #    Modo inicial (primera vez o --enviar-actuales): 🔴 sueltos y 🟢/🟡 en dos listas.
    enviados_hoy = estado["correos"].get(hoy(), 0)
    por_destino = estado.get("correos_destino", {}).get(hoy(), {})
    orden ={"🔴": 0, "🟢": 1, "🟡": 2, "🟣": 3}
    nuevos.sort(key=lambda x: orden[clasificar.nivel(x[0])[0]])
    avisados = 0
    lista_verdes, lista_amarillos = [], []
    pendientes = estado.setdefault("resumen_pendiente", [])
    rojos_enviados = 0
    for p, motivo in nuevos:
        color, etiqueta = clasificar.nivel(p)
        iconos = clasificar.iconos(p)
        texto = avisos.texto_aviso(p, color, etiqueta, iconos, motivo)
        corto = {"precio": p["precio"], "municipio": p["municipio"], "barrio": p["barrio"],
                 "metros": p["metros"], "habitaciones": p["habitaciones"],
                 "particular": bool(p["particular"]), "url": p["url"], "motivo": motivo,
                 "color": color if color != "🟡" else ""}
        filas_csv.append(color)
        if PRUEBA:
            if len(filas_csv) <= 12:
                print("-" * 60 + "\n" + texto.replace("<b>", "").replace("</b>", "") + "\n" + p["url"])
            continue
        if MODO_INICIAL:
            if color == "🔴" and (not MUESTRA or rojos_enviados < 2):
                try:
                    avisos.avisar(texto, p["url"], p["fotos"][0] if p["fotos"] else None, silencio=True,
                                  whatsapp=avisos.enlace_whatsapp(p))
                    rojos_enviados += 1
                    time.sleep(3.5)  # Telegram limita a ~20 mensajes por minuto en grupos
                except Exception as e:
                    print("ERROR avisando:", e)
            elif color == "🟢":
                lista_verdes.append(corto)
            elif color == "🟡":
                lista_amarillos.append(corto)
            continue
        # 4a. Correo automático ANTES del aviso, para poder decir en el aviso si ya les hemos escrito
        #     (solo pisos nuevos de los niveles elegidos, con tope diario y máx. 3 al mismo destinatario)
        estado_correo = ""
        if config.ENVIAR_CORREOS and not motivo and color in config.CORREO_SOLO_NIVELES:
            dest = (p["email"] or "").strip()
            h = respuestas.huella(dest) if dest else ""
            if not dest or re.search(r"no-?reply|donotreply", dest, re.I):
                estado_correo = "⚠️ Sin email: llamad o rellenad el formulario del anuncio"
            elif enviados_hoy >= config.MAX_CORREOS_POR_DIA:
                estado_correo = "⏳ Tope de correos de hoy alcanzado: contactad vosotros"
            elif por_destino.get(h, 0) >= 3:
                estado_correo = "ℹ️ Ya les hemos escrito hoy por otros pisos"
            elif correo.configurado():
                try:
                    correo.enviar(p)
                    enviados_hoy += 1
                    por_destino[h] = por_destino.get(h, 0) + 1
                    estado.setdefault("contactados", []).append(
                        {"destino": h, "municipio": p["municipio"], "precio": p["precio"], "url": p["url"], "fecha": hoy()})
                    estado_correo = "✉️ Ya les hemos escrito un correo"
                    print("  correo enviado")
                    quien = p["anunciante"] or ("Particular" if p["particular"] else "Anunciante")
                    try:
                        avisos.mensaje_html(f"✉️ <b>Escrito a {html.escape(quien)}</b> · {html.escape(p['municipio'])} · "
                                            f"{p['precio']} € · <a href=\"{html.escape(p['url'], quote=True)}\">ver anuncio</a>",
                                            silencio=True, chats=[os.environ["TELEGRAM_SEGUIMIENTO_ID"]]
                                            if os.environ.get("TELEGRAM_SEGUIMIENTO_ID") else None)
                    except Exception as e:
                        print("  ERROR apuntando en seguimiento:", e)
                    time.sleep(5)
                except Exception as e:
                    print("ERROR enviando correo:", e)
                    estado_correo = "⚠️ No se pudo enviar el correo: contactad vosotros"
        if color in ("🔴", "🟢"):
            texto += "\n\n" + bloque_que_hacer(p, color, estado_correo)
        elif estado_correo:
            texto += f"\n<b>{html.escape(estado_correo)}</b>"

        if color in ("🔴", "🟢") and avisados < config.MAX_AVISOS_POR_EJECUCION:
            try:
                avisos.avisar(texto, p["url"], p["fotos"][0] if p["fotos"] else None,
                              silencio=(color == "🟢"), whatsapp=avisos.enlace_whatsapp(p))
                avisados += 1
            except Exception as e:
                print("ERROR avisando:", e)
                pendientes.append(corto)
        elif color != "🟣":
            # 🟡, o 🔴/🟢 que no caben en esta ejecución: al resumen del día
            pendientes.append(corto)
    estado["correos"] = {hoy(): enviados_hoy}
    estado["correos_destino"] = {hoy(): por_destino}
    estado["contactados"] = estado.get("contactados", [])[-2000:]

    # 4b. Respuestas de agencias/propietarios -> grupo de seguimiento
    if not PRUEBA and not ACTUALES:
        try:
            respuestas.revisar(estado)
        except Exception as e:
            print("ERROR leyendo respuestas:", e)

    # 5. Modo inicial: listas de 🟢 y 🟡 con enlace (sin Excel)
    if MODO_INICIAL and not PRUEBA and filas_csv:
        n = {c: filas_csv.count(c) for c in ("🔴", "🟢", "🟡")}
        try:
            avisos.mensaje_html(f"🤖 <b>Pisos que YA estaban publicados</b>: {len(filas_csv)} "
                                f"({n['🔴']} 🔴 · {n['🟢']} 🟢 · {n['🟡']} 🟡). "
                                f"Arriba los 🔴 uno a uno; aquí abajo las listas. "
                                f"A partir de ahora, solo los NUEVOS.", silencio=True)
            if MUESTRA:
                lista_verdes, lista_amarillos = lista_verdes[:8], lista_amarillos[:8]
            avisos.lista(f"🟢 INTERESANTES ({n['🟢']})", sorted(lista_verdes, key=lambda x: x["precio"] or 0))
            avisos.lista(f"🟡 LEJOS ({n['🟡']})", sorted(lista_amarillos, key=lambda x: x["precio"] or 0))
        except Exception as e:
            print("ERROR avisando:", e)
    print(f"Por color: { {c: filas_csv.count(c) for c in ('🔴', '🟢', '🟡')} }")

    # 6. Resumen diario de los 🟡 (una vez al día, a partir de HORA_RESUMEN, hora de España)
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    fecha = ahora.strftime("%Y-%m-%d")
    if (not PRUEBA and not ACTUALES and ahora.hour >= config.HORA_RESUMEN
            and estado.get("ultimo_resumen") != fecha):
        if pendientes:
            try:
                avisos.lista(f"🟡 RESUMEN DEL DÍA – LEJOS ({len(pendientes)})",
                             sorted(pendientes, key=lambda x: x["precio"] or 0))
                estado["resumen_pendiente"] = []
            except Exception as e:
                print("ERROR mandando el resumen:", e)
        estado["ultimo_resumen"] = fecha

    # --enviar-actuales es una prueba/reenvío: NO toca la memoria del robot
    if not PRUEBA and not ACTUALES:
        estado["primera_vez"] = False
        guardar_estado(estado)


if __name__ == "__main__":
    main()
