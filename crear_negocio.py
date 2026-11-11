"""Crea la demo personalizada de una peluquería. Ejecutar con:  python crear_negocio.py

Te hace unas preguntas (nombre, teléfono, horario, servicios...) y guarda negocios/<nombre>.json.
Después, el enlace  https://TU-WEB/?n=<nombre>  abre la demo con los datos de ESA peluquería.
"""
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

import agenda

CARPETA = Path(__file__).parent / "negocios"
DIAS = agenda.DIAS


def pregunta(texto, defecto=None):
    sufijo = f" [{defecto}]" if defecto else ""
    while True:
        r = input(f"{texto}{sufijo}: ").strip()
        if r:
            return r
        if defecto is not None:
            return defecto


def si_no(texto, defecto="s"):
    return pregunta(texto + " (s/n)", defecto).lower().startswith("s")


def hacer_slug(nombre):
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "peluqueria"


def hora(h):
    """'9' -> '09:00', '9:30' -> '09:30', '20' -> '20:00'. Lanza ValueError si no es una hora."""
    h = h.strip().replace(".", ":")
    if ":" not in h:
        h += ":00"
    hh, mm = h.split(":")
    if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
        raise ValueError(h)
    return f"{int(hh):02d}:{int(mm):02d}"


def tramos(texto):
    """'10:00-14:00, 16:30-20:00' -> [['10:00','14:00'], ['16:30','20:00']]. Vacío o 'cerrado' -> []."""
    texto = texto.strip().lower()
    if texto in ("", "cerrado", "no", "-"):
        return []
    salida = []
    for trozo in texto.replace(" y ", ",").split(","):
        a, b = trozo.split("-")
        salida.append([hora(a), hora(b)])
    return salida


def pide_horario(texto, defecto):
    while True:
        try:
            return tramos(pregunta(texto, defecto))
        except ValueError:
            print("  No lo entiendo. Escríbelo así: 10:00-14:00, 16:30-20:00  (o 'cerrado')")


def servicios_desde_csv(ruta):
    """Fichero con líneas:  nombre;minutos;precio   (por ejemplo:  Corte de mujer;60;25)"""
    servicios, usados = [], set()
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        for fila in csv.reader(f, delimiter=";"):
            if len(fila) < 3 or not fila[1].strip().isdigit():
                continue                                    # cabecera o línea vacía
            nombre = fila[0].strip()
            sid, n = hacer_slug(nombre).replace("-", "_"), 2
            base = sid
            while sid in usados:
                sid, n = f"{base}_{n}", n + 1
            usados.add(sid)
            servicios.append({"id": sid, "nombre": nombre, "duracion_min": int(fila[1]),
                              "precio": (float(fila[2].replace(",", ".").replace("€", "").strip())
                                        if fila[2].strip() else None)})   # sin precio = "se consulta en el salón"
    return servicios


def main():
    print("\n=== Nueva demo para una peluquería ===  (Enter = valor entre corchetes)\n")
    nombre = pregunta("Nombre de la peluquería")
    slug = pregunta("Nombre corto para el enlace (sin espacios)", hacer_slug(nombre))
    slug = hacer_slug(slug)
    if slug == agenda.DEFECTO:
        sys.exit("Ese nombre está reservado para la demo de ejemplo. Elige otro.")
    direccion = pregunta("Dirección (calle y ciudad)")
    telefono = pregunta("Teléfono")
    pros = [p.strip() for p in pregunta("Profesionales que atienden a la vez, separados por comas (ej: Ana, Luis)",
                                        "Equipo").split(",") if p.strip()]
    print("\nHorario (ej: 10:00-14:00, 16:30-20:00  ·  'cerrado' si no abren)")
    lv = pide_horario("  De lunes a viernes", "10:00-14:00, 16:30-20:00")
    sab = pide_horario("  Sábado", "10:00-14:00")
    dom = pide_horario("  Domingo", "cerrado")
    horario = {d: (lv if i < 5 else sab if i == 5 else dom) for i, d in enumerate(DIAS)}

    print("\nServicios: puedes dar un fichero (líneas 'nombre;minutos;precio'; el precio puede ir vacío) o usar los de ejemplo.")
    ruta = pregunta("Ruta del fichero de servicios (Enter = usar los de ejemplo)", "")
    servicios = servicios_desde_csv(ruta) if ruta else agenda.NEGOCIO["servicios"]
    if not servicios:
        sys.exit("No he encontrado servicios en ese fichero.")

    faq = []
    if si_no("¿Aceptan tarjeta?"):
        faq.append({"p": "¿Se puede pagar con tarjeta?", "r": "Sí, aceptamos tarjeta y efectivo."})
    else:
        faq.append({"p": "¿Se puede pagar con tarjeta?", "r": "No, solo efectivo."})
    if si_no("¿Atienden sin cita si hay hueco?"):
        faq.append({"p": "¿Hay que reservar cita?", "r": "Recomendamos reservar, pero si hay hueco atendemos sin cita."})
    else:
        faq.append({"p": "¿Hay que reservar cita?", "r": "Sí, trabajamos solo con cita previa."})
    faq.append({"p": "¿Cómo se cancela una cita?",
                "r": "Avisando con al menos 4 horas de antelación, por aquí o por teléfono. Sin coste."})

    negocio = {"nombre": nombre, "direccion": direccion, "telefono": telefono, "profesionales": pros,
               "horario": horario, "servicios": servicios, "faq": faq}
    fallos = agenda.validar_negocio(negocio)
    if fallos:
        sys.exit("Hay algo mal: " + "; ".join(fallos))

    CARPETA.mkdir(exist_ok=True)
    destino = CARPETA / f"{slug}.json"
    destino.write_text(json.dumps(negocio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado en {destino}")
    print(f"Enlace de la demo:   /?n={slug}        (detrás va la dirección de tu web)")
    print(f"Tu agenda privada:   /demo?n={slug}&clave=TU_CLAVE")
    print("\nPara publicarla: git add . && git commit -m 'Demo de " + nombre + "' && git push  (Render se actualiza solo)\n")


if __name__ == "__main__":
    main()
