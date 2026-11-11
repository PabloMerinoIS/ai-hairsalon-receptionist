import os
import tempfile
from datetime import datetime

# Usa un archivo temporal para no ensuciar las citas reales
os.environ["CITAS_FILE"] = os.path.join(tempfile.mkdtemp(), "citas_test.json")

import agenda  # noqa: E402

AHORA = datetime(2026, 10, 1, 10, 0)  # jueves 1 de octubre de 2026, 10:00
VIERNES = "2026-10-02"
DOMINGO = "2026-10-04"
LUNES = "2026-10-05"


def test_cerrado_domingo_y_lunes():
    assert agenda.huecos_libres(DOMINGO, "corte_hombre", ahora=AHORA)["huecos"] == []
    assert agenda.huecos_libres(LUNES, "corte_hombre", ahora=AHORA)["huecos"] == []


def test_huecos_respetan_horario_y_duracion():
    h = agenda.huecos_libres(VIERNES, "tinte", ahora=AHORA)["huecos"]  # 120 min
    assert h[0] == "09:30"
    assert "12:00" in h and "12:30" not in h       # 12:30+2h pasa de las 14:00
    assert "16:30" in h and "18:00" in h and "18:30" not in h


def test_no_ofrece_horas_pasadas():
    ahora = datetime(2026, 10, 2, 11, 0)
    h = agenda.huecos_libres(VIERNES, "corte_hombre", ahora=ahora)["huecos"]
    assert "10:30" not in h and "11:30" in h


def test_reserva_y_capacidad_dos_profesionales():
    r1 = agenda.reservar(VIERNES, "10:00", "corte_mujer", "Ana", "611 222 333", ahora=AHORA)
    r2 = agenda.reservar(VIERNES, "10:00", "corte_mujer", "Luis", "644 555 666", ahora=AHORA)
    assert r1["ok"] and r2["ok"]
    # Con 2 profesionales ocupados, el tercero no cabe
    r3 = agenda.reservar(VIERNES, "10:00", "corte_mujer", "Eva", "655 777 888", ahora=AHORA)
    assert "error" in r3
    assert "10:00" not in r3["huecos_libres"]


def test_solapes_parciales():
    # Hay 2 citas de 60 min a las 10:00. A las 10:30 un corte de 30 min solapa con ambas.
    h = agenda.huecos_libres(VIERNES, "corte_hombre", ahora=AHORA)["huecos"]
    assert "10:30" not in h and "11:00" in h


def test_validaciones():
    assert "error" in agenda.reservar(VIERNES, "12:00", "corte_hombre", "", "611222333", ahora=AHORA)
    assert "error" in agenda.reservar(VIERNES, "12:00", "corte_hombre", "Pepe", "123", ahora=AHORA)
    assert "error" in agenda.huecos_libres("31/10/2026", "corte_hombre", ahora=AHORA)
    assert "error" in agenda.huecos_libres(VIERNES, "masaje", ahora=AHORA)


def test_cancelacion():
    r = agenda.reservar(VIERNES, "17:00", "barba", "Marta", "699 000 111", ahora=AHORA)
    cid = r["cita"]["id"]
    assert "error" in agenda.cancelar(cid, "600000000", ahora=AHORA)            # teléfono incorrecto
    assert "error" in agenda.cancelar("ZZZZZZ", "699000111", ahora=AHORA)       # código inexistente
    tarde = datetime(2026, 10, 2, 15, 0)                                         # < 4 h de la cita
    assert "error" in agenda.cancelar(cid, "699000111", ahora=tarde)
    assert agenda.cancelar(cid, "699000111", ahora=AHORA)["ok"]
    assert "17:00" in agenda.huecos_libres(VIERNES, "barba", ahora=AHORA)["huecos"]


def test_cancelar_admin_no_pide_telefono_ni_plazo():
    r = agenda.reservar(VIERNES, "18:00", "barba", "Sara", "688 777 666", ahora=AHORA)
    cid = r["cita"]["id"]
    assert agenda.cancelar_admin(cid.lower())["ok"]          # sin teléfono y en minúsculas
    assert "error" in agenda.cancelar_admin(cid)              # ya no existe
    assert "error" in agenda.cancelar_admin("")


def test_citas_entre_fechas():
    agenda.CITAS_FILE.unlink(missing_ok=True)
    agenda.reservar("2026-10-02", "10:00", "barba", "Ana", "611222333", ahora=AHORA)
    agenda.reservar("2026-10-02", "09:30", "barba", "Luis", "644555666", ahora=AHORA)
    agenda.reservar("2026-10-03", "10:00", "barba", "Eva", "655777888", ahora=AHORA)
    lista = agenda.citas_entre("2026-10-02", "2026-10-02")
    assert [c["nombre"] for c in lista] == ["Luis", "Ana"]     # ordenadas por hora
    assert len(agenda.citas_entre("2026-10-01", "2026-10-31")) == 3
    assert agenda.citas_entre("2026-11-01", "2026-11-30") == []
    assert agenda.citas_entre("no-es-fecha", "2026-11-30") is None


def test_reservas_a_la_vez_no_se_pisan():
    """Dos hilos reservando el mismo hueco: solo uno debe conseguirlo."""
    import threading
    agenda.CITAS_FILE.unlink(missing_ok=True)
    resultados = []

    def reservar(n):
        resultados.append(agenda.reservar("2026-10-02", "12:00", "corte_mujer", f"Cliente{n}", "600000000", ahora=AHORA))

    # Con 2 profesionales caben 2; lanzamos 6 y deben entrar exactamente 2
    hilos = [threading.Thread(target=reservar, args=(i,)) for i in range(6)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sum(1 for r in resultados if r.get("ok")) == 2
    assert len(agenda._cargar()) == 2


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK ", nombre)
    print("Todos los tests pasan")
