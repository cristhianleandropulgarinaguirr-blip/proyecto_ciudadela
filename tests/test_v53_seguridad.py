# tests/test_v53_seguridad.py
# Versión 5.3 · seguridad completa: sesión del administrador por inactividad, confirmar la contraseña en acciones sensibles, verificación en dos pasos (TOTP),
# login sin fuga de tiempo, tope por IP, contraseñas débiles, barrido de TODAS las rutas y cabeceras.
import os
import re
import tempfile
import time
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app import config, limitador, sesiones, totp
from app.main import app
from app.models import Auditoria, IntentoLogin, Sesion, Usuario, ahora_utc
from app.security import ALGORITHM, SECRET_KEY, _CLAVE_REAUTH

CLAVE = "claveSegura123"
ADMIN, ANA, GUARDIA = "admin@conjunto.com", "ana@conjunto.com", "celador@conjunto.com"
CSRF = {"X-Requested-With": "ciudadela"}


def dispositivo() -> TestClient:
    return TestClient(app)


def entrar(c: TestClient, email: str, codigo: str | None = None, clave: str = CLAVE):
    h = {"X-Codigo-2FA": codigo} if codigo else {}
    return c.post("/auth/login", data={"username": email, "password": clave}, headers=h)


def bearer(r) -> dict:
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def sesion_de(db, email):
    db.expire_all()
    u = db.query(Usuario).filter(Usuario.email == email).one()
    return db.query(Sesion).filter(Sesion.usuario_id == u.id).order_by(Sesion.creada.desc()).first()


@pytest.fixture()
def con_reauth(monkeypatch):
    monkeypatch.setattr(config, "REAUTH_ACTIVA", True)


# ======================================================================= 1 · sesión del administrador por inactividad
def test_las_duraciones_por_rol(db):
    admin, ana, guardia = (db.query(Usuario).filter(Usuario.email == e).one() for e in (ADMIN, ANA, GUARDIA))
    assert sesiones.vida_sesion(admin) == (timedelta(minutes=480), timedelta(hours=72))
    assert sesiones.vida_sesion(ana) == (timedelta(days=14), timedelta(days=30))
    assert sesiones.vida_sesion(guardia)[0] == timedelta(hours=12)
    assert sesiones.exige_actividad(admin) and not sesiones.exige_actividad(ana) and not sesiones.exige_actividad(guardia)


def test_admin_sin_actividad_no_alarga_la_sesion_pero_con_actividad_si(client, db):
    entrar(client, ADMIN)
    s = sesion_de(db, ADMIN)
    s.expira = ahora_utc() + timedelta(hours=2); db.commit()
    antes = s.expira
    assert client.post("/auth/refresh", headers=CSRF).status_code == 200            # una pestaña olvidada renueva el token…
    assert sesion_de(db, ADMIN).expira == antes                                       # …pero el vencimiento NO se corre
    assert client.post("/auth/refresh", headers={**CSRF, "X-Actividad": "1"}).status_code == 200
    assert sesion_de(db, ADMIN).expira > antes + timedelta(hours=5)                   # con actividad real vuelve a 8 h


def test_admin_olvidado_termina_expulsado_por_inactividad(client, db):
    entrar(client, ADMIN)
    s = sesion_de(db, ADMIN)
    s.expira = ahora_utc() - timedelta(seconds=1); db.commit()
    r = client.post("/auth/refresh", headers={**CSRF, "X-Actividad": "1"})
    assert r.status_code == 401 and "inactividad" in r.json()["detail"]


def test_residente_y_guardia_no_dependen_de_la_actividad(client, db):
    for email in (ANA, GUARDIA):
        c = dispositivo()
        entrar(c, email)
        s = sesion_de(db, email)
        s.expira = ahora_utc() + timedelta(minutes=10); db.commit()
        assert c.post("/auth/refresh", headers=CSRF).status_code == 200
        assert sesion_de(db, email).expira > ahora_utc() + timedelta(hours=1)


def test_el_tope_absoluto_del_admin_son_72_horas(client, db):
    entrar(client, ADMIN)
    s = sesion_de(db, ADMIN)
    assert timedelta(hours=71, minutes=59) < s.maxima - s.creada <= timedelta(hours=72, minutes=1)


# ======================================================================= 2 · confirmar la contraseña en acciones sensibles
NUEVO = {"nombre_completo": "Pedro Gómez", "email": "pedro@conjunto.com", "password": "otraClave2026", "rol": "Guardia"}


def test_sin_pase_las_acciones_sensibles_se_niegan_y_piden_clave(client, con_reauth):
    h = bearer(entrar(client, ADMIN))
    r = client.post("/usuarios/", json=NUEVO, headers=h)
    assert r.status_code == 403 and r.headers.get("X-Reauth-Requerida") == "1"
    for ruta in ("/reportes/cartera.xlsx", "/reportes/pqrs.xlsx", "/reportes/paquetes.xlsx", "/reportes/visitantes.xlsx", "/reportes/auditoria.xlsx"):
        assert client.get(ruta, headers=h).headers.get("X-Reauth-Requerida") == "1", ruta
    assert client.patch("/usuarios/2/activo", params={"esta_activo": False}, headers=h).headers.get("X-Reauth-Requerida") == "1"
    assert client.post("/usuarios/2/restablecer-password", headers=h).headers.get("X-Reauth-Requerida") == "1"
    assert client.patch("/usuarios/3/coeficiente", json={"coeficiente": 1.5}, headers=h).headers.get("X-Reauth-Requerida") == "1"
    assert client.post("/importaciones/residentes/aplicar", headers=h).headers.get("X-Reauth-Requerida") == "1"
    assert client.delete("/usuarios/2/2fa", headers=h).headers.get("X-Reauth-Requerida") == "1"


def test_con_la_clave_confirmada_la_accion_pasa(client, con_reauth):
    h = bearer(entrar(client, ADMIN))
    mala = client.post("/auth/reautenticar", json={"password": "incorrecta"}, headers=h)
    assert mala.status_code == 400                                                    # 400, nunca 401: la app lo leería como «sesión vencida»
    pase = client.post("/auth/reautenticar", json={"password": CLAVE}, headers=h)
    assert pase.status_code == 200 and pase.json()["expira_en"] == config.REAUTH_MINUTOS * 60
    r = client.post("/usuarios/", json=NUEVO, headers={**h, "X-Reauth": pase.json()["reauth_token"]})
    assert r.status_code == 201
    assert client.get("/reportes/cartera.xlsx", headers={**h, "X-Reauth": pase.json()["reauth_token"]}).status_code == 200


def test_el_pase_es_personal_de_la_sesion_y_vence(client, db, con_reauth):
    h = bearer(entrar(client, ADMIN))
    pase = client.post("/auth/reautenticar", json={"password": CLAVE}, headers=h).json()["reauth_token"]
    # otra sesión del mismo administrador (otro dispositivo): su pase no sirve aquí
    otro = dispositivo(); h2 = bearer(entrar(otro, ADMIN))
    assert client.post("/usuarios/", json=NUEVO, headers={**h2, "X-Reauth": pase}).status_code == 403
    # vencido
    uid = db.query(Usuario).filter(Usuario.email == ADMIN).one().id
    sid = jwt.decode(h["Authorization"].split()[1], SECRET_KEY, algorithms=[ALGORITHM])["sid"]
    viejo = jwt.encode({"usuario_id": uid, "sid": sid, "tipo": "reauth", "exp": int(time.time()) - 5}, _CLAVE_REAUTH, algorithm=ALGORITHM)
    assert client.post("/usuarios/", json=NUEVO, headers={**h, "X-Reauth": viejo}).status_code == 403
    # firmado con la clave normal (no la de reautenticación): no vale
    falso = jwt.encode({"usuario_id": uid, "sid": sid, "tipo": "reauth", "exp": int(time.time()) + 300}, SECRET_KEY, algorithm=ALGORITHM)
    assert client.post("/usuarios/", json=NUEVO, headers={**h, "X-Reauth": falso}).status_code == 403


def test_el_pase_jamas_sirve_como_token_de_acceso(client, db, con_reauth):
    h = bearer(entrar(client, ADMIN))
    pase = client.post("/auth/reautenticar", json={"password": CLAVE}, headers=h).json()["reauth_token"]
    assert client.get("/usuarios/me", headers={"Authorization": f"Bearer {pase}"}).status_code == 401


def test_un_no_administrador_recibe_403_de_rol_no_pide_clave(client, con_reauth):
    r = client.post("/usuarios/", json=NUEVO, headers=bearer(entrar(client, ANA)))
    assert r.status_code == 403 and "X-Reauth-Requerida" not in r.headers and "rol" in r.json()["detail"]


def test_adivinar_la_clave_en_reautenticar_tambien_bloquea(client, db):
    h = bearer(entrar(client, ADMIN))
    for _ in range(5):
        assert client.post("/auth/reautenticar", json={"password": "mala"}, headers=h).status_code == 400
    assert client.post("/auth/reautenticar", json={"password": CLAVE}, headers=h).status_code == 429


# ======================================================================= 3 · verificación en dos pasos
def activar_2fa(client, db, h=None):
    """Deja la cuenta del administrador con dos pasos activos. Devuelve (secreto, códigos de recuperación, paso usado al activar)."""
    h = h or bearer(entrar(client, ADMIN))
    ini = client.post("/auth/2fa/iniciar", json={"password": CLAVE}, headers=h)
    assert ini.status_code == 200, ini.text
    secreto = ini.json()["secreto"]
    paso = totp.paso_actual()
    r = client.post("/auth/2fa/activar", json={"codigo": totp._codigo(secreto, paso)}, headers=h)
    assert r.status_code == 200, r.text
    return secreto, r.json()["codigos_recuperacion"], paso


def codigo_nuevo(secreto, paso_usado):
    """Un código válido y distinto del ya usado: el del paso siguiente (se tolera un paso de desfase)."""
    return totp._codigo(secreto, paso_usado + 1)


def test_el_totp_cumple_el_vector_de_la_rfc_6238():
    secreto = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"                # «12345678901234567890»
    assert totp._codigo(secreto, 59 // 30) == "287082"
    assert totp.verificar(secreto, "287082", None, ahora=59.0) == 1
    assert totp.verificar(secreto, "287082", 1, ahora=59.0) is None     # el mismo código no se acepta dos veces
    assert totp.verificar(secreto, "000000", None, ahora=59.0) is None


def test_activar_dos_pasos_flujo_completo(client, db):
    h = bearer(entrar(client, ADMIN))
    assert client.get("/auth/2fa/estado", headers=h).json() == {"activo": False, "obligatorio": False, "codigos_restantes": 0}
    ini = client.post("/auth/2fa/iniciar", json={"password": CLAVE}, headers=h).json()
    assert ini["qr"].startswith("data:image/svg+xml") and ini["uri"].startswith("otpauth://totp/") and ini["secreto"] in ini["uri"]
    # el secreto NO queda en claro en la base
    db.expire_all()
    u = db.query(Usuario).filter(Usuario.email == ADMIN).one()
    assert u.totp_secreto and ini["secreto"] not in u.totp_secreto and totp.descifrar(u.totp_secreto) == ini["secreto"] and not u.totp_activo
    assert client.post("/auth/2fa/activar", json={"codigo": "000000"}, headers=h).status_code == 400
    r = client.post("/auth/2fa/activar", json={"codigo": totp._codigo(ini["secreto"], totp.paso_actual())}, headers=h)
    assert r.status_code == 200 and len(r.json()["codigos_recuperacion"]) == totp.N_RECUPERACION
    db.expire_all()
    u = db.query(Usuario).filter(Usuario.email == ADMIN).one()
    assert u.totp_activo and all(c not in (u.codigos_recuperacion or "") for c in r.json()["codigos_recuperacion"])    # solo hashes
    assert client.get("/auth/2fa/estado", headers=h).json()["codigos_restantes"] == totp.N_RECUPERACION
    assert db.query(Auditoria).filter(Auditoria.accion == "Activó la verificación en dos pasos").count() == 1


def test_con_dos_pasos_el_login_pide_el_codigo(client, db):
    secreto, _, paso = activar_2fa(client, db)
    c = dispositivo()
    r = entrar(c, ADMIN)                                                       # contraseña bien, sin código
    assert r.status_code == 401 and r.headers.get("X-2FA-Requerida") == "1"
    assert db.query(IntentoLogin).count() == 0                                 # pedir el código no cuenta como fallo
    r = entrar(c, ADMIN, "123456")
    assert r.status_code == 401 and r.headers.get("X-2FA-Requerida") == "1"
    assert entrar(c, ADMIN, totp._codigo(secreto, paso)).status_code == 401    # el código que ya se usó al activar no se repite
    ok = entrar(c, ADMIN, codigo_nuevo(secreto, paso))
    assert ok.status_code == 200 and c.get("/usuarios/me", headers=bearer(ok)).status_code == 200
    assert db.query(IntentoLogin).count() == 0                                 # el éxito borra los fallos


def test_un_codigo_de_dos_pasos_no_se_puede_reusar(client, db):
    secreto, _, paso = activar_2fa(client, db)
    cod = codigo_nuevo(secreto, paso)
    assert entrar(dispositivo(), ADMIN, cod).status_code == 200
    assert entrar(dispositivo(), ADMIN, cod).status_code == 401                # alguien que lo vio por encima no lo puede usar


def test_sin_la_contrasena_el_codigo_solo_no_alcanza(client, db):
    secreto, _, paso = activar_2fa(client, db)
    assert entrar(dispositivo(), ADMIN, codigo_nuevo(secreto, paso), clave="mala").status_code == 401


def test_codigo_de_recuperacion_sirve_una_sola_vez(client, db):
    _, codigos, _ = activar_2fa(client, db)
    assert entrar(dispositivo(), ADMIN, codigos[0]).status_code == 200
    assert entrar(dispositivo(), ADMIN, codigos[0]).status_code == 401
    assert entrar(dispositivo(), ADMIN, codigos[1].upper().replace("-", "")).status_code == 200     # tolera mayúsculas y sin guion
    db.expire_all()
    assert totp.quedan_recuperacion(db.query(Usuario).filter(Usuario.email == ADMIN).one().codigos_recuperacion) == totp.N_RECUPERACION - 2


def test_cinco_codigos_malos_bloquean_el_inicio_de_sesion(client, db):
    activar_2fa(client, db)
    for _ in range(5):
        assert entrar(dispositivo(), ADMIN, "111111").status_code == 401
    assert entrar(dispositivo(), ADMIN, "111111").status_code == 429


def test_activar_cierra_las_otras_sesiones(client, db):
    otro = dispositivo(); h_otro = bearer(entrar(otro, ADMIN))
    activar_2fa(client, db)
    assert otro.get("/usuarios/me", headers=h_otro).status_code == 401


def test_desactivar_exige_clave_y_codigo_y_regenerar_invalida_los_viejos(client, db):
    h = bearer(entrar(client, ADMIN))
    secreto, codigos, paso = activar_2fa(client, db, h)
    assert client.post("/auth/2fa/desactivar", json={"password": "mala", "codigo": codigo_nuevo(secreto, paso)}, headers=h).status_code == 400
    assert client.post("/auth/2fa/desactivar", json={"password": CLAVE, "codigo": "000000"}, headers=h).status_code == 400
    nuevos = client.post("/auth/2fa/codigos-nuevos", json={"password": CLAVE, "codigo": codigos[0]}, headers=h)
    assert nuevos.status_code == 200 and codigos[1] not in nuevos.json()["codigos_recuperacion"]
    assert entrar(dispositivo(), ADMIN, codigos[1]).status_code == 401        # los viejos ya no sirven
    r = client.post("/auth/2fa/desactivar", json={"password": CLAVE, "codigo": nuevos.json()["codigos_recuperacion"][0]}, headers=h)
    assert r.status_code == 200
    assert entrar(dispositivo(), ADMIN).status_code == 200                      # vuelve a entrar solo con la clave


def test_si_el_conjunto_exige_dos_pasos_no_se_pueden_quitar(client, db, monkeypatch):
    h = bearer(entrar(client, ADMIN))
    secreto, codigos, _ = activar_2fa(client, db, h)
    monkeypatch.setattr(config, "EXIGIR_2FA_ADMIN", True)
    assert client.get("/auth/2fa/estado", headers=h).json()["obligatorio"] is True
    assert client.post("/auth/2fa/desactivar", json={"password": CLAVE, "codigo": codigos[0]}, headers=h).status_code == 400


def test_solo_el_administrador_toca_los_dos_pasos(client):
    h = bearer(entrar(client, ANA))
    assert client.get("/auth/2fa/estado", headers=h).status_code == 403
    assert client.post("/auth/2fa/iniciar", json={"password": CLAVE}, headers=h).status_code == 403


def test_otro_administrador_puede_quitar_los_dos_pasos_de_un_colega(client, db):
    from app.constantes import RolNombre
    from app.models import Rol
    from app.security import encriptar_password
    r = db.query(Rol).filter(Rol.nombre == RolNombre.ADMINISTRADOR.value).one()
    db.add(Usuario(nombre_completo="Otro Admin", email="admin2@conjunto.com", password_encriptada=encriptar_password(CLAVE), rol_id=r.id)); db.commit()
    c2 = dispositivo(); h2 = bearer(entrar(c2, "admin2@conjunto.com"))
    activar_2fa(c2, db, h2)
    h1 = bearer(entrar(client, ADMIN))
    uid2 = db.query(Usuario).filter(Usuario.email == "admin2@conjunto.com").one().id
    assert client.delete(f"/usuarios/{uid2}/2fa", headers=h1).status_code == 200
    assert c2.get("/usuarios/me", headers=h2).status_code == 401              # sus sesiones se cerraron
    assert entrar(dispositivo(), "admin2@conjunto.com").status_code == 200     # y ya entra solo con la clave
    mio = db.query(Usuario).filter(Usuario.email == ADMIN).one().id
    assert client.delete(f"/usuarios/{mio}/2fa", headers=h1).status_code == 400


def test_el_script_de_rescate_quita_los_dos_pasos(client, db):
    from app import reset_2fa
    activar_2fa(client, db)
    assert entrar(dispositivo(), ADMIN).status_code == 401
    assert reset_2fa.main(ADMIN) == 0 and reset_2fa.main("nadie@x.com") == 1
    assert entrar(dispositivo(), ADMIN).status_code == 200


# ======================================================================= 4 · login: sin fuga de tiempo y con tope por IP
def test_correo_inexistente_tambien_calcula_bcrypt(client, monkeypatch):
    from app.routers import auth
    from app.security import HASH_FALSO
    usados = []
    real = auth.verificar_password
    monkeypatch.setattr(auth, "verificar_password", lambda p, h: (usados.append(h), real(p, h))[1])
    assert entrar(client, "no.existe@conjunto.com").status_code == 401
    assert usados == [HASH_FALSO]                                              # se hizo la misma comparación costosa que con un correo real
    usados.clear()
    assert entrar(client, ANA, clave="mala").status_code == 401
    assert len(usados) == 1 and usados[0] != HASH_FALSO


def test_tope_de_fallos_por_ip_aunque_cada_correo_sea_distinto(client, monkeypatch):
    monkeypatch.setattr(limitador.LOGIN_FALLOS_IP, "maximo", 4)
    for i in range(4):
        assert entrar(client, f"x{i}@conjunto.com").status_code == 401
    r = entrar(client, ANA)                                                     # ni con la clave buena: esa conexión está frenada
    assert r.status_code == 429 and "Retry-After" in r.headers


# ======================================================================= 5 · contraseñas débiles
@pytest.mark.parametrize("clave", ["12345678", "password123", "Password1", "11111111", "contraseña", "aaaaaaaa", "88888888"])
def test_contrasenas_debiles_se_rechazan(client, clave):
    h = bearer(entrar(client, ADMIN))
    r = client.post("/usuarios/", json={**NUEVO, "password": clave}, headers=h)
    assert r.status_code == 422, clave


def test_la_clave_no_puede_contener_el_correo(client):
    h = bearer(entrar(client, ADMIN))
    r = client.post("/usuarios/", json={**NUEVO, "email": "valentina.rios@conjunto.com", "password": "valentina.rios2026"}, headers=h)
    assert r.status_code == 422


def test_cambiar_password_tambien_exige_una_clave_decente(client):
    h = bearer(entrar(client, ANA))
    assert client.post("/auth/cambiar-password", json={"password_actual": CLAVE, "password_nueva": "12345678"}, headers=h).status_code == 422
    assert client.post("/auth/cambiar-password", json={"password_actual": CLAVE, "password_nueva": "miClavePropia99"}, headers=h).status_code == 200


# ======================================================================= 6 · barrido de TODAS las rutas
PUBLICAS = {("POST", "/auth/login"), ("POST", "/auth/logout"), ("POST", "/auth/refresh"), ("POST", "/demo/solicitar"),
            ("GET", "/pase-publico/{token}"), ("POST", "/pase-publico/{token}/aviso"), ("GET", "/pase-publico/{token}/imagen"),
            ("GET", "/salud"), ("GET", "/verificacion-publica/{codigo}"),
            # v5.6 · enlace de técnico de mantenimiento: sin sesión a propósito (el token del enlace es la llave; ver tests/test_v56_enlace_tecnico.py)
            ("GET", "/tecnico-publico/{token}"), ("GET", "/tecnico-publico/{token}/foto"), ("POST", "/tecnico-publico/{token}/estado")}


def _operaciones():
    for ruta, ops in sorted(app.openapi()["paths"].items()):
        for metodo, op in ops.items():
            if metodo in ("get", "post", "put", "patch", "delete"):
                yield metodo.upper(), ruta, op


def test_toda_ruta_que_no_es_publica_exige_sesion(client):
    """Si alguien agrega una ruta nueva y olvida protegerla, esta prueba falla."""
    desprotegidas = []
    for metodo, ruta, op in _operaciones():
        if (metodo, ruta) in PUBLICAS:
            continue
        concreta = re.sub(r"\{[^}]+\}", "1", ruta)
        r = client.request(metodo, concreta)
        r2 = client.request(metodo, concreta, headers={"Authorization": "Bearer token.falso.aqui"})
        if r.status_code != 401 or r2.status_code != 401:
            desprotegidas.append((metodo, ruta, r.status_code, r2.status_code))
    assert not desprotegidas, f"Rutas sin protección: {desprotegidas}"


def test_las_rutas_publicas_son_solo_las_previstas(client):
    publicas = {(m, r) for m, r, _ in _operaciones() if client.request(m, re.sub(r"\{[^}]+\}", "1", r)).status_code != 401}
    assert publicas == PUBLICAS, f"Cambió la lista de rutas públicas: {publicas ^ PUBLICAS}"


def test_las_rutas_solo_administrador_rechazan_a_un_residente(client):
    """La documentación dice «Solo **Administrador**»: aquí se comprueba que el código lo cumple de verdad (403 para un residente)."""
    h = bearer(entrar(client, ANA))
    fallos = []
    for metodo, ruta, op in _operaciones():
        texto = (op.get("description") or "") + (op.get("summary") or "")
        if not texto.lstrip().startswith("Solo **Administrador**"):
            continue
        r = client.request(metodo, re.sub(r"\{[^}]+\}", "1", ruta), headers=h)
        if r.status_code != 403:
            fallos.append((metodo, ruta, r.status_code))
    assert not fallos, f"Un residente no debería pasar: {fallos}"


# ======================================================================= 7 · cabeceras
def test_las_respuestas_con_datos_personales_no_se_guardan_en_cache(client):
    h = bearer(entrar(client, ANA))
    r = client.get("/usuarios/me", headers=h)
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["Cross-Origin-Opener-Policy"] == "same-origin" and r.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY"
    pagina = client.get("/app/")
    assert "script-src 'self'" in pagina.headers["Content-Security-Policy"] and "unsafe-inline" not in pagina.headers["Content-Security-Policy"].split("style-src")[0]


# ======================================================================= 8 · migración
def test_la_migracion_0024_agrega_y_quita_las_columnas():
    import sqlite3
    from alembic import command
    from alembic.config import Config
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta = os.path.join(tempfile.mkdtemp(), "m.db")
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(raiz, "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{ruta}")
    nuevas = {"totp_secreto", "totp_activo", "totp_ultimo_paso", "codigos_recuperacion"}
    cols = lambda: {r[1] for r in sqlite3.connect(ruta).execute("PRAGMA table_info(usuarios)")}
    command.upgrade(cfg, "head")
    assert nuevas <= cols()
    command.upgrade(cfg, "head")                                                # repetirla no rompe nada
    command.downgrade(cfg, "0023")
    assert not (nuevas & cols())
