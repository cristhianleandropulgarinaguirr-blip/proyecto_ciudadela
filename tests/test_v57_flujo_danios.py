# tests/test_v57_flujo_danios.py — v5.7 · el administrador YA NO pone «En revisión» ni «En reparación».
# Ciclo: Abierto → En Reparacion (técnico) → Solucionado (técnico) → Aprobado (administrador, al final, tras revisar la evidencia).
from app.models import Auditoria, Notificacion, ReporteDanio
from tests.test_arrendamientos import MARTA
from tests.test_v56_enlace_tecnico import ADM, ANA, LUIS, _enlace, _estado, _reporte, inquilino_activo


def _patch(client, auth, rid, estado, quien=ADM, **extra):
    return client.patch(f"/mantenimiento/cambiar-estado/{rid}", params={"nuevo_estado": estado, **extra}, headers=auth(quien))


def _solucionado_por_el_tecnico(client, auth, **kw):
    rid = _reporte(client, auth, **kw)
    e = _enlace(client, auth, rid)
    assert _estado(client, e["token"], "En Reparacion", "Ya estoy en el sitio.").status_code == 200
    assert _estado(client, e["token"], "Solucionado", "Cambié el sifón y quedó seco.").status_code == 200
    return rid


def test_el_admin_no_puede_poner_revision_ni_reparacion_ni_saltarse_al_tecnico(client, auth, db):
    rid = _reporte(client, auth)
    for estado in ("En Revision", "En Reparacion", "Solucionado", "Aprobado"):
        r = _patch(client, auth, rid, estado)
        assert r.status_code == 400, estado
    assert "técnico" in _patch(client, auth, rid, "En Reparacion").json()["detail"]
    assert "Enlace para técnico" in _patch(client, auth, rid, "Aprobado").json()["detail"]      # le dice qué hacer en su lugar
    db.expire_all()
    assert db.get(ReporteDanio, rid).estado == "Abierto"            # nada cambió


def test_ciclo_completo_el_tecnico_trabaja_y_el_admin_aprueba(client, auth, db):
    rid = _solucionado_por_el_tecnico(client, auth)
    db.expire_all()
    assert db.get(ReporteDanio, rid).estado == "Solucionado"
    assert client.get("/dashboard/kpis?refrescar=true", headers=auth(ADM)).json()["operacion"]["danios_por_aprobar"] == 1
    for quien in (ANA, LUIS):
        assert _patch(client, auth, rid, "Aprobado", quien=quien).status_code == 403          # ni el residente que reportó
    r = _patch(client, auth, rid, "Aprobado")
    assert r.status_code == 200 and r.json()["estado"] == "Aprobado"
    db.expire_all()
    assert db.query(Auditoria).filter(Auditoria.accion == "Aprobó daño").count() == 1
    assert db.query(Notificacion).filter(Notificacion.titulo == "Tu reporte fue aprobado y cerrado").count() == 1
    assert _patch(client, auth, rid, "Aprobado").status_code == 400            # ya cerrado: no se aprueba dos veces
    k = client.get("/dashboard/kpis?refrescar=true", headers=auth(ADM)).json()["operacion"]
    assert k["danios_por_aprobar"] == 0 and k["danios_sin_resolver"] == 0


def test_devolver_reabre_el_reporte_y_permite_un_enlace_nuevo(client, auth, db):
    rid = _solucionado_por_el_tecnico(client, auth)
    assert client.post(f"/mantenimiento/danios/{rid}/enlace-tecnico", json={}, headers=auth(ADM)).status_code == 400      # aún sin devolver, no hace falta
    r = _patch(client, auth, rid, "Abierto", motivo="La foto no muestra el sifón nuevo.")
    assert r.status_code == 200 and r.json()["estado"] == "Abierto"
    db.expire_all()
    aviso = db.query(Notificacion).filter(Notificacion.titulo == "Tu reporte volvió a atención").one()
    assert "La foto no muestra el sifón nuevo." in aviso.mensaje
    nuevo = _enlace(client, auth, rid)                                     # ahora sí: otro técnico (o el mismo) puede atenderlo de nuevo
    assert _estado(client, nuevo["token"], "Solucionado", "Ahora sí, con foto del sifón nuevo.").status_code == 200
    assert _patch(client, auth, rid, "Aprobado").json()["estado"] == "Aprobado"


def test_inquilino_el_propietario_tambien_se_entera_de_la_aprobacion(client, auth, db):
    inquilino_activo(client, auth, db)
    rid = _solucionado_por_el_tecnico(client, auth, email=MARTA)
    assert _patch(client, auth, rid, "Aprobado").status_code == 200
    db.expire_all()
    assert db.query(Notificacion).filter(Notificacion.titulo == "Tu reporte fue aprobado y cerrado").count() == 2     # la inquilina y su propietaria


def test_un_reporte_aprobado_no_acepta_mas_cambios_del_tecnico(client, auth):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    assert _estado(client, e["token"], "Solucionado", "Todo quedó listo y probado.").status_code == 200
    assert _patch(client, auth, rid, "Aprobado").status_code == 200
    assert _estado(client, e["token"], "En Reparacion", "Intento tardío del técnico.").status_code == 400
