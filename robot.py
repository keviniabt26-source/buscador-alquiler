"""ROBOT DE PISOS – programa principal.

Cada vez que se ejecuta:
  1. Lee los anuncios de todas las fuentes activas.
  2. Se queda con los que pasan el filtro (precio, metros, sin habitaciones…).
  3. Descarta los que ya conoce (aunque vengan de otro portal).
  4. Por cada piso NUEVO: lo clasifica (🔴🟢🟡), avisa al móvil y, si está activado,
     manda el correo de interés al anunciante.
  5. Guarda lo que ha visto en estado/estado.json.

Uso:
  python robot.py            -> funcionamiento normal
  python robot.py --prueba   -> solo mira e imprime en pantalla; no avisa ni envía nada
"""
import csv
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import avisos
import clasificar
import config
import correo
import duplicados
import fuentes

CARPETA = Path(__file__).parent
ESTADO = CARPETA / "estado" / "estado.json"
PRUEBA = "--prueba" in sys.argv


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


def main():
    cargar_env()
    estado = cargar_estado()
    primera_vez = estado.get("primera_vez", True)

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
    enviados_hoy = estado["correos"].get(hoy(), 0)
    orden = {"🔴": 0, "🟢": 1, "🟡": 2, "🟣": 3}
    nuevos.sort(key=lambda x: orden[clasificar.nivel(x[0])[0]])
    avisados = 0
    for p, motivo in nuevos:
        color, etiqueta = clasificar.nivel(p)
        iconos = clasificar.iconos(p)
        texto = avisos.texto_aviso(p, color, etiqueta, iconos, motivo)
        filas_csv.append({"nivel": color, "precio": p["precio"], "municipio": p["municipio"],
                          "barrio": p["barrio"], "habitaciones": p["habitaciones"], "metros": p["metros"],
                          "particular": "sí" if p["particular"] else "", "anunciante": p["anunciante"],
                          "telefono": p["telefono"], "email": p["email"], "detalles": " ".join(iconos),
                          "fuente": p["fuente"], "url": p["url"]})
        if PRUEBA:
            if len(filas_csv) > 12:
                continue
            print("-" * 60 + "\n" + texto.replace("<b>", "").replace("</b>", "") + "\n" + p["url"])
            continue
        if primera_vez and not config.AVISAR_EN_PRIMERA_EJECUCION:
            continue
        if avisados < config.MAX_AVISOS_POR_EJECUCION:
            try:
                avisos.avisar(texto, p["url"], p["fotos"][0] if p["fotos"] else None)
                avisados += 1
            except Exception as e:
                print("ERROR avisando:", e)
        # correo automático (solo pisos nuevos, no repetidos con bajada)
        if (config.ENVIAR_CORREOS and not motivo and p["email"] and color in config.CORREO_SOLO_NIVELES
                and enviados_hoy < config.MAX_CORREOS_POR_DIA and correo.configurado()):
            try:
                correo.enviar(p)
                enviados_hoy += 1
                print(f"  correo enviado a {p['email']}")
                time.sleep(5)
            except Exception as e:
                print("ERROR enviando correo:", e)
    estado["correos"] = {hoy(): enviados_hoy}

    # 5. Primera vez: resumen + CSV con todo lo que hay publicado ahora mismo
    if primera_vez and filas_csv:
        destino = CARPETA / "estado" / "pisos_actuales.csv"
        with open(destino, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas_csv[0].keys()), delimiter=";")
            w.writeheader()
            w.writerows(filas_csv)
        resumen = (f"🤖 Robot de pisos en marcha. Ya había {len(filas_csv)} pisos publicados que cumplen el filtro "
                   f"({sum(1 for f in filas_csv if f['nivel'] == '🔴')} 🔴, "
                   f"{sum(1 for f in filas_csv if f['nivel'] == '🟢')} 🟢, "
                   f"{sum(1 for f in filas_csv if f['nivel'] == '🟡')} 🟡). Os mando la lista en un archivo aquí abajo. "
                   f"A partir de ahora solo te aviso de los NUEVOS.")
        print(resumen)
        if not PRUEBA:
            try:
                avisos.mensaje_simple(resumen)
                avisos.documento(destino, "📋 Todos los pisos que ya estaban publicados (ábrelo con Excel)")
            except Exception as e:
                print("ERROR avisando:", e)

    if not PRUEBA:
        estado["primera_vez"] = False
        guardar_estado(estado)


if __name__ == "__main__":
    main()
