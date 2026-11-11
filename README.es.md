# Recepcionista con IA para peluquería (demo)

Un chat web donde un asistente de IA responde dudas de una peluquería (precios, horarios, preguntas frecuentes) y
reserva, consulta y cancela citas de verdad en una agenda.

## Qué hay en cada archivo

| Archivo | Para qué sirve |
|---|---|
| `crear_negocio.py` | Asistente por terminal para crear la demo de una peluquería nueva (`negocios/*.json`). |
| `negocio.json` | Datos de la peluquería: horario, servicios, precios, profesionales y preguntas frecuentes. **Cambiando esto adaptas la demo a otro negocio.** |
| `agenda.py` | Lógica de citas: huecos libres, reservas, solapes (capacidad = nº de profesionales) y cancelaciones. |
| `asistente.py` | El cerebro: Claude con tres herramientas (`consultar_huecos`, `reservar_cita`, `cancelar_cita`). |
| `app.py` | Servidor web (Flask): chat para clientes, panel de la peluquería y límites de uso. |
| `static/index.html` | La web de venta con el chat integrado. |
| `static/chat.html` | Página limpia solo con el chat, para poner detrás del botón "Pedir cita" de una web (`/chat`). |
| `static/panel.html` | El panel de citas de la peluquería. |
| `static/demo.html` | Pantalla dividida para las demos: chat + agenda juntos (`/demo`). |
| `test_agenda.py` | Tests de la agenda (no necesitan clave de API). |
| `test_panel.py` | Tests del panel y de su seguridad (tampoco necesitan clave). |

## Cómo ejecutarlo

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="tu-clave"     # en Windows (PowerShell): $env:ANTHROPIC_API_KEY="tu-clave"
python app.py
```

Abre http://localhost:5001 y habla con el asistente.

- Las citas reservadas se guardan en `citas.json` (se crea solo).
- Para comprobar todo sin gastar API: `python test_agenda.py` y `python test_panel.py`.
- Para usar otro modelo: `export MODELO="nombre-del-modelo"` (por defecto `claude-sonnet-5-5`).

## El panel de citas (`/panel`)

Abre http://localhost:5001/panel para ver la agenda como la vería la peluquera:

- **Semana de un vistazo**: los 7 días con el número de citas de cada uno. Pulsa un día para ver su lista.
- **Lista del día**: hora, cliente, servicio, teléfono (pulsable desde el móvil), precio y código de cita, con el
  total previsto. Las citas ya pasadas salen atenuadas.
- **Cancelar** una cita con un botón (no pide teléfono ni respeta el plazo de 4 horas: es para el personal).
- **+ Nueva cita**: para apuntar a mano reservas que llegan por teléfono o en persona. Solo ofrece horas libres.
- **Se actualiza sola** cada 30 segundos, así que las reservas del chat aparecen sin recargar.

## Una demo personalizada por peluquería

Para enseñarle a un dueño *su* negocio (su nombre, sus servicios, su horario):

1. Ejecuta `python crear_negocio.py` y contesta las preguntas. Si tienes su lista de precios, guárdala en un
   fichero con líneas `nombre;minutos;precio` (por ejemplo `Corte de mujer;60;25`) y dale la ruta cuando la pida.
2. Se crea `negocios/<nombre>.json`. Sube los cambios (`git add . && git commit && git push`) y Render se actualiza solo.
3. Enlace para el dueño: `https://TU-WEB/?n=<nombre>`. Tu agenda privada de esa peluquería:
   `https://TU-WEB/demo?n=<nombre>&clave=TU_CLAVE`.

Cada peluquería tiene su propia agenda y sus propios datos: no se mezclan. Si el enlace no lleva `?n=`, se usa la
peluquería de ejemplo (`negocio.json`). Al arrancar, el servidor revisa cada negocio y avisa si alguno está mal
escrito (horario al revés, servicios repetidos...) en lugar de romperse.

### La página limpia para las clientas (`/chat`)

`https://TU-WEB/chat?n=<nombre>` es una página solo con el chat, con el nombre de la peluquería y sin texto de venta.
Es la que va detrás del botón "Pedir cita" de la web de una peluquería (en vez de que el botón lleve a llamar).
Si añades `"color": "#7a5c22"` al archivo de la peluquería en `negocios/`, el chat usa el color de su marca.
La web de venta (`/?n=<nombre>`) sirve para convencer al dueño; `/chat` es lo que ven sus clientas.

## Pantalla dividida para enseñar la demo (`/demo`)

Abre http://localhost:5001/demo: el **chat a la izquierda** (lo que ve el cliente) y la **agenda a la derecha**
(lo que ve la peluquería), en la misma ventana. Cuando el asistente reserva o cancela, la agenda se actualiza al
instante, salta al día de la cita nueva y la resalta un momento. El botón "Nueva conversación" reinicia el chat.
Es la vista ideal para enseñar el producto a un dueño de peluquería. Tiene la misma protección que `/panel`.

**Seguridad**: el panel y los datos de clientes solo abren desde tu propio ordenador. Si publicas la web, define
`ADMIN_KEY` y entra con `/panel?clave=TU_CLAVE` (cualquiera sin esa clave recibe un "No autorizado"). Las acciones
que cambian datos exigen además una cabecera propia, para que ninguna otra web pueda lanzarlas desde tu navegador.
Los nombres de clientes se muestran siempre como texto, nunca se interpretan como código.

## La web (`static/index.html`)

La página principal es una web de venta ("Cita24", nombre provisional) con la demo del chat integrada arriba.
Para cambiar nombre, textos o precios edita directamente ese archivo. Los precios son de ejemplo.

Debajo del texto hay una **agenda de ejemplo** ("Lo que ve tu peluquería") que se rellena sola cuando el visitante
reserva en el chat. Es pública pero segura: cada visitante ve **solo las citas de su propia conversación**
(`/api/mi-agenda`), nunca las de otros ni las de la agenda real. Las citas hechas desde la web caducan a las 24 h
para que la demo no se llene.

Para proteger tu gasto de API cuando la publiques, el servidor limita los mensajes (se cambian con variables de
entorno): `LIMITE_IP_HORA` (por defecto 40 mensajes por hora y por IP) y `LIMITE_SESION` (30 por conversación).
Pon además un tope de gasto mensual en tu cuenta de Anthropic.

## Guion para la demo (1 minuto)

1. "Hola, quería una cita para corte de mujer mañana por la tarde." (propone huecos reales)
2. "¿Se puede pagar con tarjeta?" (responde con los datos del negocio)
3. "Me viene bien a las 17:30, soy Ana, 611 222 333." (reserva y da un código)
4. Enseña `/api/citas` para que vean la cita guardada.
5. "Quiero cancelar mi cita" (pide el código y el teléfono).
6. Pregunta algo que no esté en los datos ("¿Hacéis extensiones?"): debe decir que no lo sabe y dar el teléfono.

## Antes de ofrecérselo a un negocio real

- **Transparencia**: el asistente ya avisa de que es una IA en el primer mensaje. Mantenlo así.
- **Datos personales (RGPD)**: guardas nombre y teléfono de clientes. Hace falta un aviso de privacidad y un sitio
  seguro donde guardarlos (ahora es un simple `citas.json`).
- **Agenda real**: el siguiente paso natural es conectar `agenda.py` con Google Calendar (las tres funciones
  públicas son las únicas que habría que cambiar).
- **Estado en memoria**: las conversaciones viven en memoria del servidor; si lo reinicias, se pierden.
- **WhatsApp**: para usarlo por WhatsApp hay que pasar por la API oficial (WhatsApp Business / un proveedor como
  Twilio) y apuntarla a `asistente.responder`.

## Ideas para ampliarlo (algunas encajan con el Jarvis)

- Voz: entrada con Whisper y salida con síntesis de voz.
- Recordatorios automáticos por SMS o WhatsApp el día antes.
- Varios negocios a la vez (una carpeta con un `negocio.json` por cliente).
- Panel sencillo para que la peluquera vea y mueva las citas.
