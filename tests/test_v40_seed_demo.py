# tests/test_v40_seed_demo.py — Fase 4: el conjunto de ejemplo (python -m app.seed_demo).
import pytest
from sqlalchemy import func, select

from app import seed_demo
from app.database import Base
from app.models import Arrendamiento, PazSalvo, Reserva, Rol, Usuario, Votacion, VotacionParticipacion

CLAVE_DEMO = "Demo-clave-123"


def _conteos(db) -> dict:
    db.expire_all()
    return {t.name: db.execute(select(func.count()).select_from(t)).scalar() for t in Base.metadata.sorted_tables}


@pytest.fixture()
def demo(db):
    """El conjunto de ejemplo ya creado. (`forzar`: la base de pruebas trae dos residentes «reales» de otras pruebas.)"""
    return seed_demo.crear(db, CLAVE_DEMO, forzar=True)


def _residentes_demo(db):
    return (db.query(Usuario).join(Rol).filter(Rol.nombre == "Residente", Usuario.email.like(f"%@{seed_demo.DOMINIO}")).order_by(Usuario.id).all())


def test_crea_30_apartamentos_con_coeficientes_que_suman_exactamente_100(db, demo):
    res = _residentes_demo(db)
    assert len(res) == 30 and len({u.apartamento for u in res}) == 30
    assert round(sum(u.coeficiente for u in res), 4) == 100.0
    assert all(0 < u.coeficiente < 10 for u in res)
    assert demo["resumen"]["coeficiente_total"] == 100.0
    assert {u.apartamento.split(" Apt ")[0] for u in res} == {"Torre 1", "Torre 2"}


def test_la_cuota_es_proporcional_al_coeficiente_y_realista(db, demo):
    res = _residentes_demo(db)
    cuotas = sorted(u.valor_administracion for u in res)
    assert 150_000 <= cuotas[0] and cuotas[-1] <= 350_000 and cuotas[0] < cuotas[-1]
    mayor, menor = max(res, key=lambda u: u.coeficiente), min(res, key=lambda u: u.coeficiente)
    assert mayor.valor_administracion > menor.valor_administracion
    assert 7_500_000 <= sum(u.valor_administracion for u in res) <= 8_300_000      # cerca del presupuesto mensual


def test_seis_en_mora_y_su_estado_es_coherente(db, demo):
    res = _residentes_demo(db)
    mora = [u for u in res if not u.esta_al_dia]
    assert len(mora) == 6 == demo["resumen"]["en_mora"]
    assert all(u.saldo_pendiente > 0 for u in mora)
    assert all(u.saldo_pendiente == 0 for u in res if u.esta_al_dia)


def test_cuentas_inquilinos_y_guardias(db, demo):
    por_rol = dict(db.query(Rol.nombre, func.count(Usuario.id)).join(Usuario, Usuario.rol_id == Rol.id).filter(Usuario.email.like(f"%@{seed_demo.DOMINIO}")).group_by(Rol.nombre).all())
    assert por_rol == {"Residente": 30, "Inquilino": 5, "Guardia": 2, "Administrador": 1}
    contratos = db.query(Arrendamiento.estado, func.count()).group_by(Arrendamiento.estado).all()
    assert dict(contratos) == {"Activo": 4, "Pendiente": 1}


def test_se_puede_entrar_con_las_cuentas_de_ejemplo(client, demo):
    for rol, correo, _ in demo["cuentas"][1:]:
        r = client.post("/auth/login", data={"username": correo, "password": CLAVE_DEMO})
        assert r.status_code == 200, (rol, r.text)
    assert client.post("/auth/login", data={"username": demo["cuentas"][1][1], "password": "otra-clave"}).status_code == 401


def test_no_crea_ningun_administrador_con_clave_conocida(db, client, demo):
    admins = db.query(Usuario).join(Rol).filter(Rol.nombre == "Administrador").all()
    ejemplo = [a for a in admins if a.email.endswith(f"@{seed_demo.DOMINIO}")]
    assert len(ejemplo) == 1 and ejemplo[0].esta_activo is False
    assert client.post("/auth/login", data={"username": ejemplo[0].email, "password": CLAVE_DEMO}).status_code in (400, 401, 403)


def test_el_administrador_real_ve_todo_el_conjunto_de_ejemplo(client, auth, demo):
    h = auth("admin@conjunto.com")
    assert len(client.get("/anuncios/", headers=h).json()) == 5
    assert len(client.get("/pqrs/", headers=h).json()) == 10
    k = client.get("/dashboard/kpis", headers=h).json()
    assert k["cartera"]["unidades"] >= 30 and k["cartera"]["en_mora"] >= 6
    assert client.get("/emergencias/", headers=h).status_code == 200


def test_votaciones_coherentes_con_los_coeficientes(db, demo):
    v = db.query(Votacion).filter(Votacion.estado == "Abierta").one()
    assert v.ponderada and v.exige_al_dia and v.un_voto_por == "apartamento"
    pesos = db.query(func.sum(VotacionParticipacion.peso)).filter(VotacionParticipacion.votacion_id == v.id).scalar()
    from app.models import VotacionOpcion
    assert round(sum(o.peso for o in db.query(VotacionOpcion).filter(VotacionOpcion.votacion_id == v.id).all()), 4) == round(pesos, 4)
    # solo votaron apartamentos al día (la votación lo exige) y ninguno votó dos veces
    claves = [c for (c,) in db.query(VotacionParticipacion.clave).filter(VotacionParticipacion.votacion_id == v.id).all()]
    assert len(claves) == len(set(claves)) == 13


def test_reservas_sin_choques_y_las_futuras_son_de_quienes_estan_al_dia(db, demo):
    from app.arrendamientos import ahora_local
    filas = db.query(Reserva).filter(Reserva.estado != "Cancelada").all()
    dias = [(r.zona_comun, r.fecha_reserva.date()) for r in filas]
    assert len(dias) == len(set(dias)), "dos reservas de la misma zona el mismo día"
    futuras = [r for r in filas if r.fecha_reserva > ahora_local()]
    assert futuras and all(db.get(Usuario, r.usuario_id).esta_al_dia for r in futuras)


def test_los_paz_y_salvo_de_ejemplo_son_de_apartamentos_al_dia(db, demo):
    for p in db.query(PazSalvo).all():
        assert db.get(Usuario, p.usuario_id).esta_al_dia and not p.revocado


def test_no_corre_dos_veces_ni_sobre_una_base_con_residentes_reales(db):
    with pytest.raises(ValueError, match="residentes reales"):
        seed_demo.crear(db, CLAVE_DEMO)                      # la base de pruebas ya trae residentes
    seed_demo.crear(db, CLAVE_DEMO, forzar=True)
    with pytest.raises(ValueError, match="Ya hay datos de ejemplo"):
        seed_demo.crear(db, CLAVE_DEMO, forzar=True)


def test_los_resultados_son_siempre_los_mismos(db):
    a = seed_demo.crear(db, CLAVE_DEMO, forzar=True)["resumen"]
    seed_demo.borrar(db)
    b = seed_demo.crear(db, CLAVE_DEMO, forzar=True)["resumen"]
    assert a == b


# ------------------------------------------------------------------ borrar
def test_borrar_deja_la_base_exactamente_como_estaba(db):
    antes = _conteos(db)
    seed_demo.crear(db, CLAVE_DEMO, forzar=True)
    assert _conteos(db) != antes
    assert seed_demo.borrar(db) > 300
    assert _conteos(db) == antes
    assert seed_demo.borrar(db) == 0                          # repetirlo no hace nada ni falla


def test_borrar_tambien_limpia_lo_que_se_genero_durante_la_demostracion(db, client, demo):
    """Durante una demo se inicia sesión, se hacen reservas, se crean pases QR... y todo eso cuelga de las cuentas de ejemplo."""
    antes_demo = None
    cuenta = demo["cuentas"][1][1]
    tok = client.post("/auth/login", data={"username": cuenta, "password": CLAVE_DEMO}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/notificaciones/", headers=h).status_code == 200
    client.post("/auth/login", data={"username": cuenta, "password": "mal"})              # un fallo de login deja su contador
    client.post("/auth/login", data={"username": "otro@demo.example.com", "password": "mal"})
    assert seed_demo.borrar(db) > 0
    db.expire_all()
    assert db.query(Usuario).filter(Usuario.email.like(f"%@{seed_demo.DOMINIO}")).count() == 0
    huerfanos = {t.name: n for t, n in ((t, db.execute(select(func.count()).select_from(t)).scalar()) for t in Base.metadata.sorted_tables) if t.name in ("sesiones", "intentos_login") and n}
    assert huerfanos.get("sesiones", 0) == 0, huerfanos
    from app.models import IntentoLogin
    assert db.query(IntentoLogin).filter(IntentoLogin.clave.like("%@demo.example.com")).count() == 0
    assert antes_demo is None


def test_borrar_no_toca_los_datos_reales(db, client, auth):
    h = auth("ana@conjunto.com")
    from datetime import timedelta
    from app.arrendamientos import ahora_local
    ana = db.query(Usuario).filter(Usuario.email == "ana@conjunto.com").one()
    db.add(Reserva(usuario_id=ana.id, zona_comun="Piscina", fecha_reserva=ahora_local() + timedelta(days=40), estado="Aprobada"))
    db.commit()
    seed_demo.crear(db, CLAVE_DEMO, forzar=True)
    seed_demo.borrar(db)
    assert db.query(Usuario).filter(Usuario.email.in_(["ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com", "admin@conjunto.com"])).count() == 4
    assert db.query(Reserva).filter(Reserva.usuario_id == ana.id).count() == 1
    assert client.get("/reservas/mis-reservas", headers=h).json()[0]["zona_comun"] == "Piscina"


def test_reiniciar_equivale_a_borrar_y_crear(db):
    seed_demo.crear(db, CLAVE_DEMO, forzar=True)
    seed_demo.borrar(db)
    r = seed_demo.crear(db, "Otra-clave-456", forzar=True)
    assert r["resumen"]["apartamentos"] == 30 and r["clave"] == "Otra-clave-456"


def test_los_correos_de_ejemplo_son_validos_y_unicos(db, demo):
    from pydantic import TypeAdapter, EmailStr
    correos = [c for (c,) in db.query(Usuario.email).filter(Usuario.email.like(f"%@{seed_demo.DOMINIO}")).all()]
    assert len(correos) == len(set(correos)) == 38
    ta = TypeAdapter(EmailStr)
    assert all(ta.validate_python(c) for c in correos)
