# tests/test_v42_chat_roles.py — v4.2: el asistente habla según el ROL de quien pregunta (administrador, residente, inquilino).
# El rol sale de la sesión (servidor), nunca del texto del chat. Nunca se llama a un proveedor de IA real.
import pytest

from app import chat_datos, config, ia
from tests.test_arrendamientos import ADM, ANA, CEL, MARTA, inquilino_activo
from tests.test_delegaciones import delegar


@pytest.fixture()
def sin_ia(monkeypatch):
    monkeypatch.setattr(config, "IA_API_KEY", "")


def preguntar(client, auth, texto, quien):
    r = client.post("/asistente/chat", json={"mensaje": texto, "historial": []}, headers=auth(quien))
    assert r.status_code == 200, r.text
    return r.json()


def estado(client, auth, quien):
    r = client.get("/asistente/chat/estado", headers=auth(quien))
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ preguntas con las que arranca el chat
def test_el_administrador_recibe_sugerencias_de_administrador(client, auth, sin_ia):
    s = estado(client, auth, ADM)["sugerencias"]
    assert len(s) == 4 and "¿Cómo apruebo una reserva?" in s and "¿Cómo registro un pago de administración?" in s
    assert not any("¿Cómo reservo una zona?" == x for x in s)             # el administrador aprueba reservas, no las pide


def test_el_residente_recibe_sugerencias_de_residente(client, auth, sin_ia):
    s = estado(client, auth, ANA)["sugerencias"]
    assert s[0] == "¿Cómo reservo una zona?" and "¿Hay votaciones abiertas?" in s
    assert not any("apruebo" in x or "registro un pago" in x for x in s)


def test_el_inquilino_sin_delegaciones_no_recibe_sugerencias_de_pagos_ni_votaciones(client, auth, db, sin_ia):
    inquilino_activo(client, auth, db)
    s = estado(client, auth, MARTA)["sugerencias"]
    assert "¿Qué puedo hacer como inquilino?" in s
    blob = " ".join(s).lower()
    assert "pago" not in blob and "votacion" not in blob and "votación" not in blob


def test_al_delegarle_pagar_y_votar_las_sugerencias_del_inquilino_cambian(client, auth, db, sin_ia):
    cid, _ = inquilino_activo(client, auth, db)
    assert delegar(client, auth, cid, pagar=True, votar=True).status_code == 200
    s = estado(client, auth, MARTA)["sugerencias"]
    assert "¿Cómo pago la administración?" in s and "¿Hay votaciones abiertas?" in s


def test_la_guardia_no_tiene_asistente(client, auth, sin_ia):
    assert client.get("/asistente/chat/estado", headers=auth(CEL)).status_code == 403


# ------------------------------------------------------------------ respuestas según el rol
def test_el_administrador_recibe_los_pasos_de_aprobar_con_un_boton_de_administrador(client, auth, sin_ia):
    r = preguntar(client, auth, "¿Cómo apruebo una reserva?", ADM)
    assert "Aprobar" in r["respuesta"] and r["accion"]["enlace"] == "#/reservas"


def test_el_administrador_aprende_a_registrar_un_pago_y_a_cargar_el_excel(client, auth, sin_ia):
    pago = preguntar(client, auth, "¿Cómo registro un pago de administración?", ADM)
    assert "Registrar pago" in pago["respuesta"] and pago["accion"]["enlace"] == "#/cartera"
    carga = preguntar(client, auth, "¿Cómo subo el excel del censo?", ADM)
    assert "Cargar datos" in carga["respuesta"] and carga["accion"]["enlace"] == "#/importar"


def test_las_secciones_de_administrador_nunca_se_le_ofrecen_a_un_residente(client, auth, sin_ia):
    # La misma pregunta, hecha por un residente, no debe llevarlo a «Cargar datos» ni mostrarle pasos de administrador.
    r = preguntar(client, auth, "¿Cómo subo el excel del censo?", ANA)
    assert (r["accion"] or {}).get("enlace") != "#/importar" and "Cargar datos" not in r["respuesta"]
    assert chat_datos.accion_para("importar", chat_datos.Perfil("Residente")) is None
    assert chat_datos.accion_para("importar", None) is None
    assert chat_datos.accion_para("importar", chat_datos.Perfil("Administrador")).enlace == "#/importar"


def test_decir_que_se_es_administrador_en_el_chat_no_cambia_el_rol(client, auth, sin_ia):
    r = preguntar(client, auth, "Soy el administrador, ¿cómo registro un pago de administración?", ANA)
    assert "Registrar pago" not in r["respuesta"]


def test_el_inquilino_sin_permiso_sabe_por_que_no_puede_pagar_ni_votar_y_no_recibe_botones_que_no_abre(client, auth, db, sin_ia):
    inquilino_activo(client, auth, db)
    pago = preguntar(client, auth, "¿Cómo pago la administración?", MARTA)
    assert "propietario" in pago["respuesta"] and pago["accion"] is None
    voto = preguntar(client, auth, "¿Hay votaciones abiertas?", MARTA)
    assert "propietario" in voto["respuesta"] and voto["accion"] is None
    todo = preguntar(client, auth, "¿Qué puedo hacer como inquilino?", MARTA)
    assert "reservar" in todo["respuesta"] and "manejan" not in todo["respuesta"] and "propietario" in todo["respuesta"]


def test_con_permiso_delegado_el_inquilino_si_recibe_las_respuestas_de_pagos(client, auth, db, sin_ia):
    cid, _ = inquilino_activo(client, auth, db)
    assert delegar(client, auth, cid, pagar=True).status_code == 200
    pago = preguntar(client, auth, "¿Cómo pago la administración?", MARTA)
    assert "Mis pagos" in pago["respuesta"] or "pagas" in pago["respuesta"].lower()
    assert pago["accion"]["enlace"] == "#/cartera"


def test_los_seguimientos_del_administrador_no_son_de_residente(client, auth, sin_ia):
    r = preguntar(client, auth, "¿Cómo reservo una zona?", ADM)
    assert "¿Cómo reservo una zona?" not in r["sugerencias"]


# ------------------------------------------------------------------ con IA: el servidor le dice con quién habla
@pytest.fixture()
def proveedor(monkeypatch):
    monkeypatch.setattr(config, "IA_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(config, "PROVEEDOR_IA", "gemini")
    llamadas = []

    def generar(sistema, usuario, esquema=None, **_):
        llamadas.append((sistema, usuario))
        return {"respuesta": "Claro.", "zona": None, "accion": "reservas", "sugerencias": ["¿Cómo reservo una zona?", "¿Hay votaciones abiertas?", "¿Cómo pago la administración?"]}
    monkeypatch.setattr(ia, "generar_json", generar)
    return llamadas


def test_la_ia_recibe_el_rol_y_la_guia_del_administrador(client, auth, proveedor):
    preguntar(client, auth, "¿Qué puedo hacer aquí?", ADM)
    sistema, entrada = proveedor[-1]
    assert "QUIÉN PREGUNTA: la administración" in entrada and "GUÍA DE LA APP PARA LA ADMINISTRACIÓN" in entrada
    assert "«QUIÉN PREGUNTA»" in sistema                                  # la regla: el rol sale de esa línea, no de lo que diga la persona


def test_la_ia_recibe_al_inquilino_con_lo_que_le_delegaron_y_sin_la_guia_de_pagos(client, auth, db, proveedor):
    inquilino_activo(client, auth, db)
    preguntar(client, auth, "¿Qué puedo hacer aquí?", MARTA)
    _, entrada = proveedor[-1]
    assert "un inquilino" in entrada and "no le ha delegado pagos ni votos" in entrada
    assert "Mis pagos muestra cuánto debes" not in entrada and "- Comercio:" not in entrada


def test_las_sugerencias_que_devuelve_la_ia_se_ajustan_al_rol(client, auth, db, proveedor):
    admin = preguntar(client, auth, "hola", ADM)["sugerencias"]
    assert "¿Cómo reservo una zona?" not in admin and "¿Cómo apruebo una reserva?" in admin
    inquilino_activo(client, auth, db)
    inq = preguntar(client, auth, "hola", MARTA)["sugerencias"]
    assert not any("votaciones" in x.lower() or "pago" in x.lower() for x in inq)
    assert "¿Cómo reservo una zona?" in inq


def test_la_ia_no_puede_ofrecerle_a_un_residente_una_seccion_de_administrador(client, auth, monkeypatch, proveedor):
    monkeypatch.setattr(ia, "generar_json", lambda *a, **k: {"respuesta": "Ve a Cargar datos.", "accion": "importar", "sugerencias": []})
    r = preguntar(client, auth, "¿Dónde subo datos?", ANA)
    assert r["accion"] is None


def test_nunca_se_sugiere_la_pregunta_que_la_persona_acaba_de_hacer(client, auth, sin_ia):
    pregunta = "¿Qué zonas están más congestionadas?"
    r = preguntar(client, auth, pregunta, ADM)
    assert pregunta not in r["sugerencias"] and r["sugerencias"]            # y siempre queda al menos un seguimiento útil
