"""CONFIGURACIÓN DEL ROBOT DE PISOS
Aquí se cambia todo lo que decidimos: precios, metros, zonas y qué hacer con cada piso.
Los datos personales (teléfono, tokens, contraseñas) NO van aquí: van en los
"Secrets" de GitHub o en el archivo .env (que nunca se sube).
"""

# --- FILTRO BÁSICO -----------------------------------------------------------
PRECIO_MAXIMO = 1000          # €/mes
PRECIO_MINIMO = 250           # por debajo suele ser basura (anuncios a 0 €, plazas de parking…)
METROS_MINIMOS = 30           # si el anuncio no pone metros, pasa igual
ACEPTAR_HABITACIONES = False  # habitaciones sueltas: apagadas de momento

# --- NIVELES ------------------------------------------------------------------
# 🔴 LLAMA YA: particular en zona cercana, o precio de ganga en zona cercana
PRECIO_GANGA = 800
# Municipios cercanos, a menos de ~50 min en transporte (el resto de la
# provincia sale en 🟡 LEJOS). Se comparan sin acentos y en minúsculas.
ZONA_CERCANA = [
    # Vallès
    "barbera del valles", "badia del valles", "sabadell", "cerdanyola del valles",
    "ripollet", "montcada i reixac", "santa perpetua de mogoda", "sant quirze del valles",
    "terrassa", "polinya", "castellar del valles", "sentmenat", "matadepera",
    "palau-solita i plegamans", "mollet del valles", "la llagosta", "sant cugat del valles",
    "rubi", "sant fost de campsentelles", "martorelles", "santa maria de martorelles",
    # Barcelona y alrededores con R4 / R7 / metro
    "barcelona", "l'hospitalet de llobregat", "hospitalet de llobregat",
    "santa coloma de gramenet", "cornella de llobregat", "sant feliu de llobregat",
    "molins de rei", "esplugues de llobregat", "sant joan despi", "sant just desvern",
]

# --- CORREOS AUTOMÁTICOS ------------------------------------------------------
# Si es True y el anuncio trae el correo del anunciante, el robot le envía
# el mensaje de plantillas/correo_interes.txt desde tu Gmail.
ENVIAR_CORREOS = True         # correo automático al anunciante (Gmail del robot)
MAX_CORREOS_POR_DIA = 10      # cuenta nueva y compartida con el envío a agencias: total bajo para no parecer spam
CORREO_SOLO_NIVELES = ["🔴"]  # a qué niveles se escribe

# --- AVISOS AL MÓVIL ----------------------------------------------------------
# "telegram", "whatsapp" o "ambos"
CANAL_AVISOS = "telegram"
# La primera vez que se ejecuta hay cientos de pisos ya publicados: en vez de
# mandar cientos de avisos, los guarda como "vistos" y crea pisos_actuales.csv
AVISAR_EN_PRIMERA_EJECUCION = False
MAX_AVISOS_POR_EJECUCION = 25  # por seguridad, si algo sale mal no te inunda (lo que no quepa va al resumen)
# 🟡 LEJOS no se manda uno a uno: va en un resumen diario a partir de esta hora (hora de España)
HORA_RESUMEN = 21

# --- FUENTES ------------------------------------------------------------------
FUENTES_ACTIVAS = ["habitaclia", "fotocasa", "pisoscom"]  # milanuncios bloquea a GitHub: se usa su alerta propia
PAUSA_ENTRE_PAGINAS = 2.0     # segundos, para no cargar las webs
