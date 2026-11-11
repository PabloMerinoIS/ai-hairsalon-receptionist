"""Tests del panel: seguridad de las rutas y flujo completo (sin llamar a la API de IA)."""
import os
import tempfile

os.environ["CITAS_FILE"] = os.path.join(tempfile.mkdtemp(), "citas_panel_test.json")
os.environ.setdefault("ANTHROPIC_API_KEY", "clave-falsa-para-tests")

import agenda  # noqa: E402
import app as servidor  # noqa: E402

cliente = servidor.app.test_client()
PANEL = {"X-Panel": "1"}
PROXY = {"X-Forwarded-For": "8.8.8.8"}


def limpiar():
    agenda.CITAS_FILE.unlink(missing_ok=True)
    os.environ.pop("ADMIN_KEY", None)


def proximo_dia_abierto():
    from datetime import date, timedelta
    d = date.today() + timedelta(days=2)
    while not agenda.NEGOCIO["horario"][agenda.DIAS[d.weekday()]]:
        d += timedelta(days=1)
    return d.isoformat()


def test_panel_solo_en_local():
    limpiar()
    assert cliente.get("/panel").status_code == 200
    assert cliente.get("/panel", headers=PROXY).status_code == 403          # desde internet: no
    assert cliente.get("/api/citas", headers=PROXY).status_code == 403
    assert cliente.get("/api/admin/servicios", headers=PROXY).status_code == 403


def test_con_clave_admin():
    limpiar()
    os.environ["ADMIN_KEY"] = "secreta"
    assert cliente.get("/panel", headers=PROXY).status_code == 403
    assert cliente.get("/panel?clave=mala", headers=PROXY).status_code == 403
    assert cliente.get("/panel?clave=secreta", headers=PROXY).status_code == 200
    assert cliente.get("/api/citas?clave=secreta", headers=PROXY).status_code == 200
    os.environ.pop("ADMIN_KEY")


def test_acciones_exigen_cabecera_del_panel():
    limpiar()
    fecha = proximo_dia_abierto()
    cuerpo = {"fecha": fecha, "hora": "10:00", "servicio": "barba", "nombre": "Ana", "telefono": "611222333"}
    assert cliente.post("/api/admin/citas", json=cuerpo).status_code == 403              # sin cabecera
    assert cliente.delete("/api/citas/ABC123").status_code == 403
    assert cliente.post("/api/admin/citas", json=cuerpo, headers=PANEL).status_code == 200


def test_flujo_completo():
    limpiar()
    fecha = proximo_dia_abierto()
    cuerpo = {"fecha": fecha, "hora": "10:00", "servicio": "barba", "nombre": "<b>Ana</b>", "telefono": "611 222 333"}
    r = cliente.post("/api/admin/citas", json=cuerpo, headers=PANEL)
    assert r.status_code == 200
    cid = r.get_json()["cita"]["id"]

    lista = cliente.get(f"/api/citas?desde={fecha}&hasta={fecha}").get_json()
    assert len(lista) == 1 and lista[0]["nombre"] == "<b>Ana</b>"            # se guarda tal cual; el panel lo escapa
    assert cliente.get("/api/citas?desde=mal&hasta=peor").status_code == 400

    huecos = cliente.get(f"/api/admin/huecos?fecha={fecha}&servicio=barba").get_json()
    assert huecos["huecos"][0] == "09:30" or "10:00" in huecos["huecos"]

    # Misma hora otra vez: hay 2 profesionales, la tercera reserva ya no cabe
    cliente.post("/api/admin/citas", json={**cuerpo, "nombre": "Luis"}, headers=PANEL)
    tercera = cliente.post("/api/admin/citas", json={**cuerpo, "nombre": "Eva"}, headers=PANEL)
    assert tercera.status_code == 400

    assert cliente.delete(f"/api/citas/{cid}", headers=PANEL).status_code == 200
    assert cliente.delete(f"/api/citas/{cid}", headers=PANEL).status_code == 404
    assert len(cliente.get(f"/api/citas?desde={fecha}&hasta={fecha}").get_json()) == 1


def test_demo_pantalla_dividida():
    limpiar()
    assert cliente.get("/demo").status_code == 200
    assert cliente.get("/demo", headers=PROXY).status_code == 403            # desde internet: no
    os.environ["ADMIN_KEY"] = "secreta"
    assert cliente.get("/demo?clave=secreta", headers=PROXY).status_code == 200
    assert cliente.get("/demo?clave=mala", headers=PROXY).status_code == 403
    os.environ.pop("ADMIN_KEY")


def test_paginas_privadas_no_se_incrustan_en_otras_webs():
    limpiar()
    for ruta in ("/panel", "/demo"):
        r = cliente.get(ruta)
        assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
        assert "no-store" in r.headers["Cache-Control"]


def test_agenda_publica_solo_muestra_la_propia_sesion():
    limpiar()
    fecha = proximo_dia_abierto()
    a, b = "a" * 32, "b" * 32
    assert agenda.reservar(fecha, "10:00", "barba", "Ana", "611222333", sesion=a)["ok"]
    assert agenda.reservar(fecha, "11:00", "barba", "Luis", "622333444", sesion=b)["ok"]
    assert agenda.reservar(fecha, "12:00", "barba", "Eva", "633444555")["ok"]        # cita "real", sin sesión

    mia = cliente.get(f"/api/mi-agenda?sesion={a}", headers=PROXY)                    # público: sin permisos
    assert mia.status_code == 200
    datos = mia.get_json()
    assert [c["nombre"] for c in datos] == ["Ana"]
    assert "sesion" not in datos[0] and "creada" not in datos[0]
    assert cliente.get("/api/mi-agenda?sesion=" + "c" * 32, headers=PROXY).get_json() == []
    for mala in ("", "x", "../../etc", "A" * 32, "a" * 31):                            # ids mal formados: nada
        assert cliente.get("/api/mi-agenda", query_string={"sesion": mala}, headers=PROXY).get_json() == []
    assert "no-store" in mia.headers["Cache-Control"]


def test_citas_de_la_demo_caducan():
    limpiar()
    from datetime import datetime, timedelta
    fecha = proximo_dia_abierto()
    agenda.reservar(fecha, "10:00", "barba", "Vieja", "611222333", sesion="a" * 32)
    citas = agenda._cargar()
    citas[0]["creada"] = (datetime.now() - timedelta(hours=25)).isoformat()
    agenda._guardar(citas)
    agenda.reservar(fecha, "11:00", "barba", "Nueva", "622333444", sesion="b" * 32)
    assert [c["nombre"] for c in agenda._cargar()] == ["Nueva"]


def test_varias_peluquerias_no_se_mezclan(monkeypatch=None):
    limpiar()
    import json
    otra = json.loads(json.dumps(agenda.NEGOCIO))
    otra.update(nombre="Peluquería Lola", profesionales=["Lola"])
    assert agenda.validar_negocio(otra) == []
    agenda.NEGOCIOS["lola"] = otra
    try:
        fecha = proximo_dia_abierto()
        assert cliente.get("/api/negocio?n=lola").get_json()["nombre"] == "Peluquería Lola"
        assert cliente.get("/api/negocio?n=noexiste").get_json()["nombre"] == agenda.NEGOCIO["nombre"]
        cuerpo = {"fecha": fecha, "hora": "10:00", "servicio": "barba", "nombre": "Ana", "telefono": "611222333"}
        assert cliente.post("/api/admin/citas?n=lola", json=cuerpo, headers=PANEL).status_code == 200
        # Lola tiene 1 profesional: la segunda a la misma hora ya no cabe; en la demo (2 profesionales) sí
        assert cliente.post("/api/admin/citas?n=lola", json={**cuerpo, "nombre": "Luis"}, headers=PANEL).status_code == 400
        assert cliente.post("/api/admin/citas", json={**cuerpo, "nombre": "Luis"}, headers=PANEL).status_code == 200
        assert [c["nombre"] for c in cliente.get("/api/citas?n=lola").get_json()] == ["Ana"]
        assert [c["nombre"] for c in cliente.get("/api/citas").get_json()] == ["Luis"]
        # la agenda pública de cada visitante también está separada por peluquería
        assert agenda.reservar(fecha, "12:00", "barba", "Eva", "633444555", sesion="e" * 32, negocio="lola")["ok"]
        assert cliente.get("/api/mi-agenda?sesion=" + "e" * 32 + "&n=lola").get_json()[0]["nombre"] == "Eva"
        assert cliente.get("/api/mi-agenda?sesion=" + "e" * 32).get_json() == []
    finally:
        agenda.NEGOCIOS.pop("lola", None)
        agenda._archivo("lola").unlink(missing_ok=True)


def test_validar_negocio_detecta_errores():
    import json
    malo = json.loads(json.dumps(agenda.NEGOCIO))
    malo["horario"]["lunes"] = [["20:00", "10:00"]]
    malo["servicios"].append(dict(malo["servicios"][0]))
    fallos = " ".join(agenda.validar_negocio(malo))
    assert "lunes" in fallos and "repetido" in fallos
    del malo["faq"]
    assert "faq" in " ".join(agenda.validar_negocio(malo))


def test_pagina_de_chat_limpia_y_color_de_marca():
    limpiar()
    assert cliente.get("/chat", headers=PROXY).status_code == 200            # pública: la usan las clientas
    assert cliente.get("/api/negocio?n=estilo-luna").get_json()["color"] == "#7a5c22"
    assert cliente.get("/api/negocio").get_json()["color"] is None
    import json
    malo = json.loads(json.dumps(agenda.NEGOCIO)); malo["color"] = "rojo"
    assert "color" in " ".join(agenda.validar_negocio(malo))


def test_no_hay_ruta_static_publica():
    limpiar()
    assert cliente.get("/static/panel.html").status_code == 404
    assert cliente.get("/static/panel.html", headers=PROXY).status_code == 404


def test_chat_sigue_publico():
    limpiar()
    assert cliente.get("/", headers=PROXY).status_code == 200
    assert cliente.get("/api/negocio", headers=PROXY).status_code == 200


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK ", nombre)
    print("Todos los tests del panel pasan")
