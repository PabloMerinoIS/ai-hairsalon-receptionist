"""Agenda de citas de la peluquería: huecos libres, reservas y cancelaciones.

Las citas se guardan en citas.json (o en la ruta de la variable CITAS_FILE).
Más adelante se puede cambiar por Google Calendar sin tocar el resto.
"""
import json
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent
CITAS_FILE = Path(os.environ.get("CITAS_FILE", BASE / "citas.json"))
DEFECTO = "demo"  # el negocio de ejemplo (negocio.json); los demás viven en la carpeta negocios/
# El chat y el panel pueden escribir a la vez: este cerrojo evita que una escritura pise a otra
_LOCK = threading.RLock()

PASO_MIN = 30
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


# ---------- negocios (uno por peluquería) ----------
def validar_negocio(n):
    """Devuelve una lista de problemas del negocio (vacía si está bien)."""
    fallos = []
    for campo in ("nombre", "direccion", "telefono", "profesionales", "horario", "servicios", "faq"):
        if campo not in n:
            fallos.append(f"falta '{campo}'")
    if fallos:
        return fallos
    if "color" in n and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(n["color"])):
        fallos.append("'color' debe ser un color como #7a5c22")
    if not n["profesionales"]:
        fallos.append("'profesionales' no puede estar vacío")
    for d in DIAS:
        if d not in n["horario"]:
            fallos.append(f"el horario no tiene '{d}'")
            continue
        for tramo in n["horario"][d]:
            try:
                a, b = (datetime.strptime(h, "%H:%M") for h in tramo)
                if a >= b:
                    fallos.append(f"horario de {d}: {tramo[0]} no es anterior a {tramo[1]}")
            except (ValueError, TypeError):
                fallos.append(f"horario de {d} no válido: {tramo}")
    ids = set()
    for sv in n["servicios"]:
        try:
            if sv["id"] in ids:
                fallos.append(f"servicio repetido: {sv['id']}")
            ids.add(sv["id"])
            if int(sv["duracion_min"]) <= 0:
                fallos.append(f"duración no válida en '{sv['id']}'")
            if sv["precio"] is not None:      # precio vacío (null) = "se consulta en el salón"
                float(sv["precio"])
        except (KeyError, ValueError, TypeError):
            fallos.append(f"servicio mal formado: {sv}")
    return fallos


def cargar_negocios():
    """Lee negocio.json (slug 'demo') y todos los negocios/*.json (slug = nombre del archivo)."""
    negocios = {}
    archivos = [(DEFECTO, BASE / "negocio.json")] + [(f.stem, f) for f in sorted((BASE / "negocios").glob("*.json"))]
    for slug, ruta in archivos:
        try:
            n = json.loads(ruta.read_text(encoding="utf-8"))
            fallos = validar_negocio(n)
        except (OSError, ValueError) as e:
            fallos = [str(e)]
        if fallos:
            print(f"AVISO: el negocio '{slug}' no se carga: " + "; ".join(fallos))
            continue
        negocios[slug] = n
    return negocios


NEGOCIOS = cargar_negocios()
NEGOCIO = NEGOCIOS[DEFECTO]      # atajo al negocio de ejemplo


def negocio_de(slug=None):
    """El negocio con ese slug; si no existe, el de ejemplo."""
    return NEGOCIOS.get(slug or DEFECTO) or NEGOCIOS[DEFECTO]


def slug_valido(slug):
    return slug if slug in NEGOCIOS else DEFECTO


def _archivo(slug):
    slug = slug_valido(slug)
    if slug == DEFECTO:
        return CITAS_FILE
    return CITAS_FILE.with_name(f"{CITAS_FILE.stem}_{slug}{CITAS_FILE.suffix}")


# ---------- utilidades ----------
def _cargar(negocio=DEFECTO):
    f = _archivo(negocio)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return []


def _guardar(citas, negocio=DEFECTO):
    _archivo(negocio).write_text(json.dumps(citas, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_fecha(fecha_str):
    try:
        return datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_hora(d, hora_str):
    return datetime.strptime(f"{d.isoformat()} {hora_str}", "%Y-%m-%d %H:%M")


def buscar_servicio(texto, negocio=DEFECTO):
    """Busca un servicio por id o por parte del nombre (sin mayúsculas)."""
    servicios = negocio_de(negocio)["servicios"]
    t = (texto or "").strip().lower()
    for s in servicios:
        if t == s["id"] or t == s["nombre"].lower():
            return s
    for s in servicios:
        if t and (t in s["nombre"].lower() or t in s["id"]):
            return s
    return None


def _ocupadas_en(citas, inicio, fin):
    n = 0
    for c in citas:
        ci = datetime.fromisoformat(c["inicio"])
        cf = datetime.fromisoformat(c["fin"])
        if ci < fin and cf > inicio:
            n += 1
    return n


# ---------- funciones públicas ----------
def huecos_libres(fecha_str, servicio_str, ahora=None, negocio=DEFECTO):
    """Devuelve los huecos libres de un día para un servicio."""
    ahora = ahora or datetime.now()
    neg = negocio_de(negocio)
    d = _parse_fecha(fecha_str)
    if d is None:
        return {"error": "Fecha no válida. Usa el formato AAAA-MM-DD."}
    servicio = buscar_servicio(servicio_str, negocio)
    if servicio is None:
        return {"error": f"No reconozco el servicio '{servicio_str}'.",
                "servicios_disponibles": [s["nombre"] for s in neg["servicios"]]}

    tramos = neg["horario"][DIAS[d.weekday()]]
    if not tramos:
        return {"fecha": fecha_str, "servicio": servicio["nombre"], "huecos": [],
                "nota": f"Ese día ({DIAS[d.weekday()]}) la peluquería está cerrada."}

    citas = [c for c in _cargar(negocio) if c["fecha"] == fecha_str]
    capacidad = len(neg["profesionales"])
    dur = timedelta(minutes=servicio["duracion_min"])
    huecos = []
    for ini_t, fin_t in tramos:
        cursor = _parse_hora(d, ini_t)
        limite = _parse_hora(d, fin_t)
        while cursor + dur <= limite:
            if cursor > ahora and _ocupadas_en(citas, cursor, cursor + dur) < capacidad:
                huecos.append(cursor.strftime("%H:%M"))
            cursor += timedelta(minutes=PASO_MIN)
    return {"fecha": fecha_str, "dia": DIAS[d.weekday()], "servicio": servicio["nombre"],
            "duracion_min": servicio["duracion_min"], "precio": servicio["precio"], "huecos": huecos}


DEMO_HORAS = 24  # las citas hechas desde la web pública de demo se borran solas pasado este tiempo


def _reservar(fecha_str, hora_str, servicio_str, nombre, telefono, ahora=None, sesion=None, negocio=DEFECTO):
    nombre = (nombre or "").strip()
    telefono = "".join(ch for ch in (telefono or "") if ch.isdigit())
    if len(nombre) < 2:
        return {"error": "Falta el nombre del cliente."}
    if len(telefono) < 9:
        return {"error": "El teléfono no parece válido (mínimo 9 dígitos)."}

    libres = huecos_libres(fecha_str, servicio_str, ahora=ahora, negocio=negocio)
    if "error" in libres:
        return libres
    if hora_str not in libres["huecos"]:
        return {"error": f"Las {hora_str} ya no están disponibles.", "huecos_libres": libres["huecos"]}

    servicio = buscar_servicio(servicio_str, negocio)
    d = _parse_fecha(fecha_str)
    inicio = _parse_hora(d, hora_str)
    fin = inicio + timedelta(minutes=servicio["duracion_min"])
    cita = {
        "id": uuid.uuid4().hex[:6].upper(),
        "fecha": fecha_str,
        "inicio": inicio.isoformat(),
        "fin": fin.isoformat(),
        "servicio": servicio["nombre"],
        "precio": servicio["precio"],
        "nombre": nombre,
        "telefono": telefono,
    }
    citas = _cargar(negocio)
    if sesion:
        # Cita hecha desde la web pública: se liga a la conversación y caduca, para que la demo no se llene
        cita["sesion"] = sesion
        cita["creada"] = datetime.now().isoformat()
        limite = datetime.now() - timedelta(hours=DEMO_HORAS)
        citas = [c for c in citas if not (c.get("sesion") and datetime.fromisoformat(c["creada"]) < limite)]
    citas.append(cita)
    _guardar(citas, negocio)
    return {"ok": True, "cita": cita}


def _cancelar(cita_id, telefono, ahora=None, negocio=DEFECTO):
    ahora = ahora or datetime.now()
    telefono = "".join(ch for ch in (telefono or "") if ch.isdigit())
    citas = _cargar(negocio)
    for c in citas:
        if c["id"] == (cita_id or "").strip().upper():
            if c["telefono"] != telefono:
                return {"error": "El teléfono no coincide con el de la reserva."}
            if datetime.fromisoformat(c["inicio"]) - ahora < timedelta(hours=4):
                return {"error": "Quedan menos de 4 horas para la cita. Para cancelarla hay que llamar al "
                                 f"{negocio_de(negocio)['telefono']}."}
            citas.remove(c)
            _guardar(citas, negocio)
            return {"ok": True, "cancelada": c}
    return {"error": "No encuentro ninguna cita con ese código."}


# ---------- funciones públicas (con cerrojo) ----------
def reservar(fecha_str, hora_str, servicio_str, nombre, telefono, ahora=None, sesion=None, negocio=DEFECTO):
    """Reserva una cita si el hueco sigue libre."""
    with _LOCK:
        return _reservar(fecha_str, hora_str, servicio_str, nombre, telefono, ahora=ahora, sesion=sesion,
                         negocio=negocio)


def cancelar(cita_id, telefono, ahora=None, negocio=DEFECTO):
    """Cancela una cita con su código y el teléfono con el que se reservó (la usa el cliente desde el chat)."""
    with _LOCK:
        return _cancelar(cita_id, telefono, ahora=ahora, negocio=negocio)


def cancelar_admin(cita_id, negocio=DEFECTO):
    """Cancela una cita desde el panel de la peluquería: sin pedir teléfono ni respetar el plazo."""
    with _LOCK:
        citas = _cargar(negocio)
        for c in citas:
            if c["id"] == (cita_id or "").strip().upper():
                citas.remove(c)
                _guardar(citas, negocio)
                return {"ok": True, "cancelada": c}
    return {"error": "No encuentro ninguna cita con ese código."}


def citas_entre(desde, hasta, negocio=DEFECTO):
    """Citas con fecha entre `desde` y `hasta` (AAAA-MM-DD, ambas incluidas), ordenadas por hora."""
    if _parse_fecha(desde) is None or _parse_fecha(hasta) is None:
        return None
    with _LOCK:
        citas = [c for c in _cargar(negocio) if desde <= c["fecha"] <= hasta]
    return sorted(citas, key=lambda c: c["inicio"])


def citas_de_sesion(sesion, negocio=DEFECTO):
    """Citas hechas desde una conversación concreta (para la agenda pública de la demo).

    Solo devuelve los campos que el propio visitante ya conoce; nunca las citas de otros.
    """
    if not sesion:
        return []
    with _LOCK:
        citas = [c for c in _cargar(negocio) if c.get("sesion") == sesion]
    campos = ("id", "fecha", "inicio", "fin", "servicio", "precio", "nombre", "telefono")
    return [{k: c[k] for k in campos} for c in sorted(citas, key=lambda c: c["inicio"])]
