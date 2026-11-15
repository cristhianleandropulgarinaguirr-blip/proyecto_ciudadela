# tests/test_v38_coeficiente_votos.py — Versión 3.8, Fase 3 (legal): coeficiente de copropiedad y votación ponderada (Ley 675).
import io
from datetime import timedelta

from app.models import Auditoria, Usuario, VotacionOpcion, VotacionParticipacion, ahora_utc
from tests.test_arrendamientos import ADM, ANA, CEL, LUIS, inquilino_activo
from tests.test_delegaciones import delegar, id_de


def poner(client, auth, db, email, valor, quien=ADM):
    return client.patch(f"/usuarios/{id_de(db, email)}/coeficiente", json={"coeficiente": valor}, headers=auth(quien))


def con_coeficientes(client, auth, db, ana=60.0, luis=40.0):
    assert poner(client, auth, db, ANA, ana).status_code == 200
    assert poner(client, auth, db, LUIS, luis).status_code == 200


def ponderada(client, auth, **extra):
    cuerpo = {"titulo": "¿Aprobamos la cuota extraordinaria?", "opciones": ["Sí", "No"], "ponderada": True,
              "fecha_cierre": (ahora_utc() + timedelta(days=3)).isoformat() + "Z", **extra}
    return client.post("/votaciones/", json=cuerpo, headers=auth(ADM))


def opciones(client, auth, vid):
    return {o["texto"]: o for o in client.get(f"/votaciones/{vid}", headers=auth(ADM)).json()["opciones"]}


def votar(client, auth, quien, vid, texto):
    oid = opciones(client, auth, vid)[texto]["id"]
    return client.post(f"/votaciones/{vid}/votar", json={"opcion_id": oid}, headers=auth(quien))


# ================================================================ asignar el coeficiente
def test_el_administrador_asigna_el_coeficiente_y_queda_en_auditoria(client, auth, db):
    r = poner(client, auth, db, ANA, 0.85234)
    assert r.status_code == 200 and r.json()["coeficiente"] == 0.8523          # se guarda con 4 decimales
    assert db.query(Auditoria).filter(Auditoria.accion == "Asignó coeficiente").count() == 1


def test_solo_el_administrador_y_solo_a_propietarios(client, auth, db):
    assert poner(client, auth, db, ANA, 1.0, quien=ANA).status_code == 403
    assert poner(client, auth, db, ANA, 1.0, quien=CEL).status_code == 403
    assert poner(client, auth, db, CEL, 1.0).status_code == 400                # un guardia no es propietario
    assert client.patch("/usuarios/9999/coeficiente", json={"coeficiente": 1}, headers=auth(ADM)).status_code == 404


def test_valores_invalidos(client, auth, db):
    for malo in (0, -1, 100.5, "abc"):
        assert poner(client, auth, db, ANA, malo).status_code == 422


def test_la_suma_no_puede_pasar_de_100(client, auth, db):
    assert poner(client, auth, db, ANA, 70).status_code == 200
    r = poner(client, auth, db, LUIS, 40)
    assert r.status_code == 400 and "100" in r.json()["detail"]
    assert poner(client, auth, db, LUIS, 30).status_code == 200                # justo 100: sí


def test_quitar_el_coeficiente_con_null(client, auth, db):
    poner(client, auth, db, ANA, 10)
    r = poner(client, auth, db, ANA, None)
    assert r.status_code == 200 and r.json()["coeficiente"] is None


def test_resumen_dice_que_apartamentos_faltan_y_cuando_esta_completo(client, auth, db):
    r = client.get("/usuarios/coeficientes/resumen", headers=auth(ADM)).json()
    assert r["apartamentos"] == 2 and r["con_coeficiente"] == 0 and not r["completo"] and len(r["sin_coeficiente"]) == 2
    poner(client, auth, db, ANA, 60)
    r = client.get("/usuarios/coeficientes/resumen", headers=auth(ADM)).json()
    assert r["con_coeficiente"] == 1 and r["sin_coeficiente"] == ["Torre 2 Apt 202"] and r["total"] == 60 and not r["completo"]
    poner(client, auth, db, LUIS, 40)
    r = client.get("/usuarios/coeficientes/resumen", headers=auth(ADM)).json()
    assert r["completo"] and r["total"] == 100 and r["sin_coeficiente"] == []
    assert client.get("/usuarios/coeficientes/resumen", headers=auth(ANA)).status_code == 403


def test_dos_propietarios_del_mismo_apartamento_cuentan_una_sola_vez(client, auth, db):
    from app.models import Rol
    from app.security import encriptar_password
    rol = db.query(Rol).filter(Rol.nombre == "Residente").one()
    db.add(Usuario(nombre_completo="Pedro Copropietario", email="pedro@conjunto.com", password_encriptada=encriptar_password("claveSegura123"), rol_id=rol.id, apartamento="torre 1  apt 101"))
    db.commit()
    poner(client, auth, db, ANA, 60)
    assert poner(client, auth, db, "pedro@conjunto.com", 60).status_code == 200      # mismo apartamento: no suma 120
    assert client.get("/usuarios/coeficientes/resumen", headers=auth(ADM)).json()["total"] == 60


# ================================================================ carga masiva
def csv(contenido: str):
    return {"archivo": ("censo.csv", io.BytesIO(contenido.encode("utf-8")), "text/csv")}


def test_la_plantilla_trae_la_columna_coeficiente(client, auth):
    r = client.get("/importaciones/plantilla/residentes", headers=auth(ADM))
    assert r.status_code == 200
    from openpyxl import load_workbook
    libro = load_workbook(io.BytesIO(r.content))
    assert "coeficiente" in [c.value for c in libro["Datos"][1]]


def test_el_censo_importa_el_coeficiente_con_coma_o_punto(client, auth, db):
    texto = ("nombre_completo;email;apartamento;coeficiente\n"
             "Ana Residente;ana@conjunto.com;Torre 1 Apt 101;0,8523\n"
             "Luis Residente;luis@conjunto.com;Torre 2 Apt 202;1.5 %\n")
    r = client.post("/importaciones/residentes/aplicar", files=csv(texto), headers=auth(ADM))
    assert r.status_code == 200, r.text
    assert db.query(Usuario).filter(Usuario.email == ANA).one().coeficiente == 0.8523
    assert db.query(Usuario).filter(Usuario.email == LUIS).one().coeficiente == 1.5


def test_coeficiente_mal_escrito_es_un_error_de_esa_fila(client, auth, db):
    texto = "nombre_completo;email;apartamento;coeficiente\nAna Residente;ana@conjunto.com;Torre 1 Apt 101;mucho\n"
    r = client.post("/importaciones/residentes/vista-previa", files=csv(texto), headers=auth(ADM))
    assert r.status_code == 200 and r.json()["errores"] == 1 and "Coeficiente" in r.json()["filas"][0]["mensaje"]


def test_una_planilla_que_hace_pasar_de_100_se_rechaza(client, auth, db):
    texto = ("nombre_completo;email;apartamento;coeficiente\n"
             "Ana Residente;ana@conjunto.com;Torre 1 Apt 101;70\n"
             "Luis Residente;luis@conjunto.com;Torre 2 Apt 202;45\n")
    r = client.post("/importaciones/residentes/vista-previa", files=csv(texto), headers=auth(ADM))
    assert r.status_code == 400 and "100" in r.json()["detail"]
    assert db.query(Usuario).filter(Usuario.email == ANA).one().coeficiente is None


# ================================================================ votación ponderada
def test_no_se_puede_crear_si_faltan_coeficientes(client, auth, db):
    poner(client, auth, db, ANA, 60)
    r = ponderada(client, auth)
    assert r.status_code == 400 and "Torre 2 Apt 202" in r.json()["detail"]


def test_ponderada_exige_un_voto_por_apartamento(client, auth, db):
    con_coeficientes(client, auth, db)
    assert ponderada(client, auth, un_voto_por="persona").status_code == 422


def test_cada_voto_vale_el_coeficiente_del_apartamento(client, auth, db):
    con_coeficientes(client, auth, db, 60, 40)
    v = ponderada(client, auth, resultados_en_vivo=True)
    assert v.status_code == 201 and v.json()["ponderada"] is True and v.json()["coeficiente_total"] == 100
    vid = v.json()["id"]
    assert votar(client, auth, ANA, vid, "Sí").status_code == 200
    ya = client.get(f"/votaciones/{vid}", headers=auth(ADM)).json()
    assert ya["quorum_coeficiente"] == 60 and ya["participacion"] == 1
    assert votar(client, auth, LUIS, vid, "No").status_code == 200
    r = client.get(f"/votaciones/{vid}", headers=auth(ADM)).json()
    por_texto = {o["texto"]: o for o in r["opciones"]}
    assert por_texto["Sí"]["coeficiente"] == 60 and por_texto["Sí"]["porcentaje"] == 60.0
    assert por_texto["No"]["coeficiente"] == 40 and por_texto["No"]["porcentaje"] == 40.0
    assert r["quorum_coeficiente"] == 100 and r["total_votos"] == 2


def test_un_apartamento_pequeno_no_pesa_igual_que_uno_grande(client, auth, db):
    con_coeficientes(client, auth, db, 90, 10)
    vid = ponderada(client, auth, resultados_en_vivo=True).json()["id"]
    votar(client, auth, ANA, vid, "No")
    votar(client, auth, LUIS, vid, "Sí")
    o = opciones(client, auth, vid)
    assert o["No"]["porcentaje"] == 90.0 and o["Sí"]["porcentaje"] == 10.0       # 1 voto contra 1 voto, pero 90 % contra 10 %


def test_el_residente_ve_cuanto_vale_su_voto(client, auth, db):
    con_coeficientes(client, auth, db, 60, 40)
    vid = ponderada(client, auth).json()["id"]
    assert client.get(f"/votaciones/{vid}", headers=auth(ANA)).json()["tu_coeficiente"] == 60
    assert client.get(f"/votaciones/{vid}", headers=auth(LUIS)).json()["tu_coeficiente"] == 40


def test_el_voto_sigue_siendo_secreto_en_las_ponderadas(client, auth, db):
    con_coeficientes(client, auth, db)
    vid = ponderada(client, auth).json()["id"]
    votar(client, auth, ANA, vid, "Sí")
    assert not hasattr(VotacionParticipacion, "opcion_id")                       # la participación no guarda qué votó
    assert db.query(VotacionParticipacion).one().peso == 60
    assert client.get(f"/votaciones/{vid}/participacion", headers=auth(ADM)).status_code == 200
    assert client.get(f"/votaciones/{vid}", headers=auth(LUIS)).json()["opciones"][0]["votos"] is None   # resultados ocultos hasta cerrar


def test_participacion_incluye_el_coeficiente_que_falta(client, auth, db):
    con_coeficientes(client, auth, db, 60, 40)
    vid = ponderada(client, auth).json()["id"]
    votar(client, auth, ANA, vid, "Sí")
    p = client.get(f"/votaciones/{vid}/participacion", headers=auth(ADM)).json()
    assert p["participaron"] == ["Torre 1 Apt 101"] and p["coeficiente_participaron"] == 60 and p["coeficiente_pendientes"] == 40


def test_si_a_un_apartamento_le_quitan_el_coeficiente_no_puede_votar(client, auth, db):
    con_coeficientes(client, auth, db)
    vid = ponderada(client, auth).json()["id"]
    poner(client, auth, db, LUIS, None)
    r = votar(client, auth, LUIS, vid, "Sí")
    assert r.status_code == 400 and "coeficiente" in r.json()["detail"]
    assert db.query(VotacionParticipacion).count() == 0                          # no quedó registrado un voto sin peso


def test_el_inquilino_con_el_voto_delegado_vota_con_el_coeficiente_del_propietario(client, auth, db):
    con_coeficientes(client, auth, db, 60, 40)
    cid, inq = inquilino_activo(client, auth, db)
    assert delegar(client, auth, cid, votar=True).status_code == 200
    vid = ponderada(client, auth, resultados_en_vivo=True).json()["id"]
    r = client.post(f"/votaciones/{vid}/votar", json={"opcion_id": opciones(client, auth, vid)["Sí"]["id"]}, headers=inq)
    assert r.status_code == 200 and opciones(client, auth, vid)["Sí"]["coeficiente"] == 60
    assert votar(client, auth, ANA, vid, "No").status_code == 409                # el apartamento ya votó: no vota dos veces


def test_una_votacion_normal_no_cambia(client, auth, db):
    v = client.post("/votaciones/", json={"titulo": "¿Pintamos?", "opciones": ["Sí", "No"], "fecha_cierre": (ahora_utc() + timedelta(days=2)).isoformat() + "Z", "resultados_en_vivo": True}, headers=auth(ADM))
    assert v.status_code == 201 and v.json()["ponderada"] is False and v.json()["quorum_coeficiente"] is None
    vid = v.json()["id"]
    assert votar(client, auth, ANA, vid, "Sí").status_code == 200
    assert opciones(client, auth, vid)["Sí"]["porcentaje"] == 100.0 and opciones(client, auth, vid)["Sí"]["coeficiente"] is None
    assert db.query(VotacionOpcion).filter(VotacionOpcion.peso != 0).count() == 0
