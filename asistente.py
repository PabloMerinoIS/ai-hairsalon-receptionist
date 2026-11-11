"""Cerebro del asistente: Claude con herramientas para consultar huecos, reservar y cancelar."""
import json
import os
from datetime import datetime

import anthropic

import agenda

MODELO = os.environ.get("MODELO", "claude-sonnet-5-5")
client = anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

HERRAMIENTAS = [
    {
        "name": "consultar_huecos",
        "description": "Devuelve los huecos libres de un día concreto para un servicio. "
                       "Úsala siempre antes de proponer una hora.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {"type": "string", "description": "Fecha en formato AAAA-MM-DD"},
                "servicio": {"type": "string", "description": "Nombre o id del servicio"},
            },
            "required": ["fecha", "servicio"],
        },
    },
    {
        "name": "reservar_cita",
        "description": "Reserva una cita. Solo úsala cuando el cliente haya confirmado fecha, hora y servicio "
                       "y te haya dado su nombre y teléfono.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {"type": "string", "description": "AAAA-MM-DD"},
                "hora": {"type": "string", "description": "HH:MM en 24 horas"},
                "servicio": {"type": "string"},
                "nombre": {"type": "string"},
                "telefono": {"type": "string"},
            },
            "required": ["fecha", "hora", "servicio", "nombre", "telefono"],
        },
    },
    {
        "name": "cancelar_cita",
        "description": "Cancela una cita existente con su código y el teléfono de la reserva.",
        "input_schema": {
            "type": "object",
            "properties": {
                "codigo": {"type": "string", "description": "Código de 6 caracteres de la cita"},
                "telefono": {"type": "string"},
            },
            "required": ["codigo", "telefono"],
        },
    },
]


def _ejecutar(nombre, args, sesion=None, negocio=agenda.DEFECTO):
    if nombre == "consultar_huecos":
        return agenda.huecos_libres(args["fecha"], args["servicio"], negocio=negocio)
    if nombre == "reservar_cita":
        return agenda.reservar(args["fecha"], args["hora"], args["servicio"], args["nombre"], args["telefono"],
                               sesion=sesion, negocio=negocio)
    if nombre == "cancelar_cita":
        return agenda.cancelar(args["codigo"], args["telefono"], negocio=negocio)
    return {"error": f"Herramienta desconocida: {nombre}"}


def _system_prompt(negocio=agenda.DEFECTO):
    n = agenda.negocio_de(negocio)
    hoy = datetime.now()
    servicios = "\n".join(
        f"- {s['nombre']}: {s['duracion_min']} min, " +
        (f"{s['precio']} €" if s["precio"] is not None else "precio NO disponible (no lo inventes: di que se confirma en el salón)")
        for s in n["servicios"])
    horario = "\n".join(
        f"- {d.capitalize()}: " + (" y ".join(f"{a}-{b}" for a, b in t) if t else "cerrado")
        for d, t in n["horario"].items()
    )
    faq = "\n".join(f"P: {f['p']}\nR: {f['r']}" for f in n["faq"])
    return f"""Eres el asistente virtual de {n['nombre']} ({n['direccion']}, tel. {n['telefono']}).
Hablas en español, con tono cercano, amable y breve (mensajes cortos, como en WhatsApp).
Hoy es {DIAS_ES[hoy.weekday()]} {hoy.strftime('%Y-%m-%d')} y son las {hoy.strftime('%H:%M')}.

En tu primer mensaje deja claro que eres un asistente de IA.

SERVICIOS:
{servicios}

HORARIO:
{horario}

PREGUNTAS FRECUENTES:
{faq}

REGLAS:
- Responde SOLO con la información de arriba. Si no sabes algo, dilo y ofrece el teléfono {n['telefono']}.
- Nunca inventes precios, horarios, servicios ni huecos.
- Para proponer una hora, consulta siempre primero con consultar_huecos. Ofrece como mucho 3 opciones.
- Antes de reservar, confirma con el cliente servicio, día, hora y pide nombre y teléfono.
- Tras reservar, repite los datos y dale el código de la cita (lo necesitará para cancelar).
- Convierte expresiones como "mañana" o "el viernes" a fechas AAAA-MM-DD usando la fecha de hoy.
- No des consejos médicos ni de salud capilar; para eso, que consulten con el equipo.
- Si el cliente pide algo que no puedes hacer, ofrece llamar al {n['telefono']}."""


def responder(historial, sesion=None, negocio=agenda.DEFECTO):
    """Recibe la lista de mensajes (formato Anthropic) y devuelve el texto de respuesta.

    Modifica `historial` añadiendo los turnos del asistente y de las herramientas.
    """
    for _ in range(6):  # límite de seguridad de vueltas con herramientas
        resp = client.messages.create(
            model=MODELO,
            max_tokens=800,
            system=_system_prompt(negocio),
            tools=HERRAMIENTAS,
            messages=historial,
        )
        historial.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")

        resultados = []
        for b in resp.content:
            if b.type == "tool_use":
                salida = _ejecutar(b.name, b.input, sesion, negocio)
                resultados.append({
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": json.dumps(salida, ensure_ascii=False),
                })
        historial.append({"role": "user", "content": resultados})

    return "Perdona, me he liado. ¿Me lo puedes repetir o llamar al " + agenda.negocio_de(negocio)["telefono"] + "?"
