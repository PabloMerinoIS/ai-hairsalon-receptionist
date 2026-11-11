"""Servidor web del chat y del panel de citas. Ejecutar con: python app.py y abrir http://localhost:5001

- Chat para clientes:       http://localhost:5001
- Panel de la peluquería:   http://localhost:5001/panel
"""
import hmac
import os
import re
import time
import uuid
from collections import defaultdict, deque

from flask import Flask, jsonify, request, send_from_directory

import agenda
import asistente

# Sin ruta /static automática: cada página se sirve a mano, así el panel queda protegido
app = Flask(__name__, static_folder=None)
CONVERSACIONES = {}  # id de sesión -> historial de mensajes

# Límites para proteger el gasto de API cuando la demo sea pública
LIMITE_IP_HORA = int(os.environ.get("LIMITE_IP_HORA", 40))    # mensajes por hora y por IP
LIMITE_SESION = int(os.environ.get("LIMITE_SESION", 30))      # mensajes por conversación
_visitas = defaultdict(deque)
SESION_VALIDA = re.compile(r"^[0-9a-f]{32}$")


# ---------- utilidades ----------
def _ip_cliente():
    # Detrás de un servicio de alojamiento la IP real llega en X-Forwarded-For
    reenviada = request.headers.get("X-Forwarded-For", "")
    return (reenviada.split(",")[0].strip() or request.remote_addr or "desconocida")


def _ip_excede_limite(ip):
    ahora = time.time()
    cola = _visitas[ip]
    while cola and ahora - cola[0] > 3600:
        cola.popleft()
    if len(cola) >= LIMITE_IP_HORA:
        return True
    cola.append(ahora)
    return False


def _negocio():
    """Qué peluquería se está usando: viene en ?n=slug (o en el cuerpo del chat). Si no existe, la de ejemplo."""
    return agenda.slug_valido(request.args.get("n") or (request.get_json(silent=True) or {}).get("negocio"))


def _mensajes_del_usuario(historial):
    return sum(1 for m in historial if m["role"] == "user" and isinstance(m["content"], str))


def _es_admin():
    """El panel y los datos de clientes están protegidos.

    - Si defines ADMIN_KEY, hay que entrar con ?clave=TU_CLAVE
    - Si no la defines, solo funcionan desde tu propio ordenador (localhost).
    """
    clave = os.environ.get("ADMIN_KEY")
    if clave:
        return hmac.compare_digest(request.args.get("clave", ""), clave)
    return request.remote_addr in ("127.0.0.1", "::1") and not request.headers.get("X-Forwarded-For")


def _prohibido(escritura=False):
    """Devuelve una respuesta de error si no se puede entrar, o None si todo está bien."""
    if not _es_admin():
        return jsonify({"error": "No autorizado"}), 403
    # Las acciones que cambian datos exigen una cabecera propia: otra web no puede enviarla desde tu navegador
    if escritura and request.headers.get("X-Panel") != "1":
        return jsonify({"error": "Petición no válida"}), 403
    return None


# ---------- chat de clientes ----------
@app.get("/")
def inicio():
    return send_from_directory("static", "index.html")


@app.get("/chat")
def pagina_chat():
    """Página limpia solo con el chat (sin texto de venta): la que iría detrás del botón "Pedir cita" de una web."""
    return send_from_directory("static", "chat.html")


@app.get("/api/negocio")
def negocio():
    n = agenda.negocio_de(_negocio())
    return jsonify({"nombre": n["nombre"], "color": n.get("color")})


@app.post("/api/chat")
def chat():
    datos = request.get_json(silent=True) or {}
    texto = (datos.get("mensaje") or "").strip()
    if not texto:
        return jsonify({"error": "Mensaje vacío"}), 400
    if len(texto) > 500:
        return jsonify({"error": "Mensaje demasiado largo"}), 400

    if _ip_excede_limite(_ip_cliente()):
        return jsonify({"error": "Límite de mensajes por hora alcanzado"}), 429

    neg = _negocio()
    sesion = datos.get("sesion")
    if not (isinstance(sesion, str) and SESION_VALIDA.match(sesion)):
        sesion = uuid.uuid4().hex       # id inventado o mal formado: se crea uno nuevo
    historial = CONVERSACIONES.setdefault(sesion, [])
    if _mensajes_del_usuario(historial) >= LIMITE_SESION:
        return jsonify({"error": "Límite de mensajes de la conversación alcanzado"}), 429

    historial.append({"role": "user", "content": texto})
    try:
        respuesta = asistente.responder(historial, sesion, neg)
    except Exception as e:  # noqa: BLE001
        historial.pop()
        return jsonify({"error": f"Error del asistente: {e}"}), 500
    return jsonify({"respuesta": respuesta, "sesion": sesion})


@app.get("/api/mi-agenda")
def mi_agenda():
    """Agenda pública de la demo: cada visitante ve solo las citas que ha hecho en su propia conversación."""
    sesion = request.args.get("sesion", "")
    citas = agenda.citas_de_sesion(sesion, _negocio()) if SESION_VALIDA.match(sesion) else []
    respuesta = jsonify(citas)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


# ---------- panel de la peluquería ----------
@app.after_request
def proteger_paginas_privadas(respuesta):
    # El panel y la pantalla dividida solo pueden mostrarse dentro de esta misma web, nunca en otra
    if request.path in ("/panel", "/demo"):
        respuesta.headers["X-Frame-Options"] = "SAMEORIGIN"
        respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app.get("/panel")
def panel():
    if not _es_admin():
        return ("No autorizado. Si has publicado la web, entra con /panel?clave=TU_CLAVE "
                "(la clave es la variable ADMIN_KEY)."), 403
    return send_from_directory("static", "panel.html")


@app.get("/demo")
def demo():
    """Pantalla dividida para enseñar la demo: el chat a la izquierda y la agenda a la derecha."""
    if not _es_admin():
        return ("No autorizado. Si has publicado la web, entra con /demo?clave=TU_CLAVE "
                "(la clave es la variable ADMIN_KEY)."), 403
    return send_from_directory("static", "demo.html")


@app.get("/api/citas")
def citas():
    """Citas reservadas. Con ?desde=AAAA-MM-DD&hasta=AAAA-MM-DD filtra por fechas."""
    if (r := _prohibido()):
        return r
    desde, hasta = request.args.get("desde"), request.args.get("hasta")
    if desde or hasta:
        lista = agenda.citas_entre(desde or "0000-01-01", hasta or "9999-12-31", _negocio())
        if lista is None:
            return jsonify({"error": "Fechas no válidas. Usa AAAA-MM-DD."}), 400
        return jsonify(lista)
    return jsonify(sorted(agenda._cargar(_negocio()), key=lambda c: c["inicio"]))


@app.delete("/api/citas/<cita_id>")
def cancelar_cita(cita_id):
    if (r := _prohibido(escritura=True)):
        return r
    res = agenda.cancelar_admin(cita_id, _negocio())
    return jsonify(res), (200 if res.get("ok") else 404)


@app.get("/api/admin/servicios")
def admin_servicios():
    if (r := _prohibido()):
        return r
    return jsonify([{"id": s["id"], "nombre": s["nombre"], "duracion_min": s["duracion_min"], "precio": s["precio"]}
                    for s in agenda.negocio_de(_negocio())["servicios"]])


@app.get("/api/admin/huecos")
def admin_huecos():
    if (r := _prohibido()):
        return r
    res = agenda.huecos_libres(request.args.get("fecha", ""), request.args.get("servicio", ""), negocio=_negocio())
    return jsonify(res), (400 if "error" in res else 200)


@app.post("/api/admin/citas")
def admin_nueva_cita():
    """Alta de una cita a mano (por ejemplo, una reserva hecha por teléfono)."""
    if (r := _prohibido(escritura=True)):
        return r
    d = request.get_json(silent=True) or {}
    res = agenda.reservar(d.get("fecha"), d.get("hora"), d.get("servicio"), d.get("nombre"), d.get("telefono"),
                          negocio=agenda.slug_valido(request.args.get("n")))
    return jsonify(res), (200 if res.get("ok") else 400)


if __name__ == "__main__":
    # Puerto 5001 por defecto: en Mac el 5000 lo ocupa AirPlay. Se puede cambiar con PORT=xxxx
    puerto = int(os.environ.get("PORT", 5001))
    print(f"\n  Chat:    http://localhost:{puerto}\n  Panel:   http://localhost:{puerto}/panel\n"
          f"  Demo:    http://localhost:{puerto}/demo   (chat y agenda en la misma pantalla)\n")
    app.run(host="0.0.0.0", port=puerto, debug=False)
