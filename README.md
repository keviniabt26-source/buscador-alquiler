# Buscador de alquiler

Robot en Python que vigila varios portales inmobiliarios y avisa por **Telegram** en cuanto aparece un piso de alquiler que cumple unos filtros.

Se ejecuta solo cada 15 minutos con **GitHub Actions**, sin servidor propio y sin coste.

## Qué hace en cada ejecución

1. **Lee** los anuncios de varias fuentes (si una falla, las demás siguen).
2. **Filtra** por precio máximo, metros mínimos y tipo de inmueble.
3. **Quita duplicados**: el mismo piso anunciado en dos portales se detecta por la huella de la foto (dHash), por el contacto o por la combinación municipio + precio + metros.
4. **Clasifica** cada piso nuevo por prioridad (🔴 urgente, 🟢 bueno, 🟡 lejos) según zona, precio y si lo anuncia un particular.
5. **Avisa** por Telegram con foto, datos clave y un botón al anuncio.
6. **Recuerda** lo que ya ha visto (`estado/estado.json`) para avisar solo de lo nuevo, y de las bajadas de precio.

## Estructura

| Archivo | Para qué sirve |
|---|---|
| `robot.py` | Programa principal |
| `config.py` | Filtros y opciones (precio, metros, zonas, fuentes) |
| `fuentes.py` | Lectura de cada portal |
| `duplicados.py` | Detección de pisos repetidos |
| `clasificar.py` | Filtro y nivel de prioridad |
| `avisos.py` | Envío a Telegram |
| `.github/workflows/robot.yml` | Horario de GitHub Actions |

## Privacidad

- Los datos sensibles (token del bot, chat de destino, clave de huellas) van en **GitHub Secrets**, nunca en el código.
- No se publican datos de contacto de los anunciantes: para detectar duplicados solo se guarda una huella con clave secreta.
- Las peticiones van espaciadas para no cargar las webs.

## Uso local

```bash
pip install -r requirements.txt
python robot.py --prueba   # solo muestra lo que encontraría, no avisa
```
