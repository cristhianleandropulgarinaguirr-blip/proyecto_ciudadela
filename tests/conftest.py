# tests/conftest.py
# Las variables de entorno se fijan ANTES de importar la app: así las pruebas
# usan una base de datos temporal y nunca tocan la tuya.
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="pruebas_conjunto_")
os.environ["SECRET_KEY"] = "clave-de-pruebas-solo-para-tests-0123456789abcdef"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/pruebas.db"
os.environ["UPLOAD_DIR"] = f"{_TMP}/uploads"
os.environ.setdefault("BCRYPT_ROUNDS", "4")   # bcrypt rápido solo en pruebas (en producción son 12 rondas)

# Las pruebas NO deben depender de tu archivo .env (ahí tienes tus valores reales: claves push, correo, IA, etc.).
# Se fijan aquí, antes de importar la app, y load_dotenv() no sobrescribe lo que ya está definido.
_VALORES_DE_PRUEBA = {
    "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
    "GUARDIA_TOKEN_HORAS": "12",
    "SESION_DIAS_ADMIN": "7",
    "SESION_DIAS": "14",
    "SESION_MAXIMA_DIAS": "60",
    "VAPID_PUBLIC_KEY": "",      # sin claves push: así se prueba el modo «apagado»
    "VAPID_PRIVATE_KEY": "",
    "SMTP_HOST": "",             # sin correo real
    "IA_API_KEY": "",            # sin IA real
    "GEMINI_API_KEY": "",
    "PROVEEDOR_IA": "gemini",
    "IA_MODELO": "",
    "IA_URL_BASE": "",
    "ALMACEN": "local",          # nunca Supabase real
    "SUPABASE_URL": "",
    "SUPABASE_SECRET_KEY": "",
    "PAGOS_SIMULADOS": "1",
    # v5.3: valores de la landing/demo y de marca. Si tu .env real los define (p. ej. tu WhatsApp), antes se colaban en las pruebas
    # y hacían fallar test_sin_whatsapp_configurado_no_hay_numero_en_la_pagina. Aquí se fijan «vacíos» o por defecto.
    "MODO_DEMO": "0",
    "LANDING_ACTIVA": "1",
    "DOCS_ACTIVAS": "1",
    "DEMO_WHATSAPP": "",
    "DEMO_CONTACTO": "",
    "DEMO_CORREO": "",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "MARCA_COLOR": "",
}
os.environ.update(_VALORES_DE_PRUEBA)

import pytest
from fastapi.testclient import TestClient

from app import limitador
from app.routers import dashboard as _dashboard
from app.database import Base, SessionLocal, engine
from app.main import app
from app.seed import asegurar_roles, crear_admin
from app.constantes import RolNombre
from app.models import Rol, Usuario
from app.security import encriptar_password

CLAVE = "claveSegura123"


@pytest.fixture()
def db():
    _dashboard.reiniciar_cache()    # los indicadores se guardan 60 s: cada prueba los calcula de nuevo
    limitador.reiniciar_todo()      # los contadores de abuso (IP, PIN) viven en memoria: cada prueba empieza en cero
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as sesion:
        asegurar_roles(sesion)
        crear_admin(sesion, "admin@conjunto.com", "Admin", CLAVE)
        for email, nombre, rol, apto in [
            ("celador@conjunto.com", "Celador Uno", RolNombre.GUARDIA, None),
            ("ana@conjunto.com", "Ana Residente", RolNombre.RESIDENTE, "Torre 1 Apt 101"),
            ("luis@conjunto.com", "Luis Residente", RolNombre.RESIDENTE, "Torre 2 Apt 202"),
        ]:
            r = sesion.query(Rol).filter(Rol.nombre == rol.value).one()
            sesion.add(Usuario(nombre_completo=nombre, email=email, password_encriptada=encriptar_password(CLAVE),
                               rol_id=r.id, apartamento=apto))
        sesion.commit()
        yield sesion


@pytest.fixture()
def client(db):
    return TestClient(app)


@pytest.fixture()
def auth(client):
    """auth('ana@conjunto.com') -> encabezados con el token de ese usuario."""
    def _auth(email: str) -> dict:
        r = client.post("/auth/login", data={"username": email, "password": CLAVE})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _auth
