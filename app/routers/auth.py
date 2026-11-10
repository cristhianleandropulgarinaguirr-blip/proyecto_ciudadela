# app/routers/auth.py
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auditoria import auditar
from app.database import get_db
from app.dependencies import get_current_user
from app.config import GUARDIA_TOKEN_HORAS
from app.constantes import RolNombre
from app.models import IntentoLogin, Usuario, ahora_utc
from app.schemas.negocio import MensajeResponse
from app.schemas.usuarios import CambioPassword, TokenResponse
from app.security import crear_token_acceso, encriptar_password, es_hash_antiguo, verificar_password

router = APIRouter(prefix="/auth", tags=["Autenticación"])

MAX_FALLOS = 5            # intentos fallidos seguidos permitidos
BLOQUEO_MINUTOS = 15      # cuánto dura el bloqueo; también es la "memoria" del contador


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión y obtener el token JWT",
    description="Recibe `username` (el correo) y `password` como formulario. Devuelve un token JWT "
    "firmado que se envía en el encabezado `Authorization: Bearer <token>`. "
    "En Swagger usa el botón **Authorize** (candado) para probar las rutas protegidas. "
    "Las cuentas las crea el administrador en `POST /usuarios/`.",
    responses={401: {"description": "Credenciales incorrectas"}, 403: {"description": "Usuario desactivado"},
               429: {"description": "Demasiados intentos fallidos: espera unos minutos"}},
)
def login_usuario(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ahora = ahora_utc()
    clave = form.username.strip().lower()
    intento = db.query(IntentoLogin).filter(IntentoLogin.clave == clave).first()

    # Límite de intentos: tras 5 fallos seguidos ese correo queda bloqueado 15 minutos. Se cuenta por el correo
    # escrito (exista o no), así tampoco se descubre qué cuentas existen mirando quién se bloquea.
    if intento and intento.bloqueado_hasta and intento.bloqueado_hasta > ahora:
        minutos = max(1, int((intento.bloqueado_hasta - ahora).total_seconds() // 60) + 1)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} min.",
                            headers={"Retry-After": str(minutos * 60)})

    usuario = db.query(Usuario).filter(Usuario.email == form.username).first()

    # Mismo mensaje para "no existe" y "clave incorrecta": no revela qué correos están registrados.
    if usuario is None or not verificar_password(form.password, usuario.password_encriptada):
        if intento is None:
            intento = IntentoLogin(clave=clave, fallos=0)
            db.add(intento)
        if intento.ultimo_intento and intento.ultimo_intento < ahora - timedelta(minutes=BLOQUEO_MINUTOS):
            intento.fallos = 0                      # los fallos viejos no cuentan
        intento.fallos += 1
        intento.ultimo_intento = ahora
        if intento.fallos >= MAX_FALLOS:
            intento.bloqueado_hasta, intento.fallos = ahora + timedelta(minutes=BLOQUEO_MINUTOS), 0
            auditar(db, None, "Bloqueó inicio de sesión", "Seguridad", usuario.id if usuario else None,
                    f"{MAX_FALLOS} intentos fallidos con «{clave[:80]}»; bloqueado {BLOQUEO_MINUTOS} min")
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not usuario.esta_activo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado.")
    if intento:                                     # entró bien: el contador vuelve a cero
        db.delete(intento)
        db.commit()

    # Migración transparente: si la clave estaba con el SHA-256 antiguo, se pasa a bcrypt.
    if es_hash_antiguo(usuario.password_encriptada):
        usuario.password_encriptada = encriptar_password(form.password)
        db.commit()

    minutos = GUARDIA_TOKEN_HORAS * 60 if usuario.rol == RolNombre.GUARDIA.value else None
    token = crear_token_acceso({"sub": usuario.email, "usuario_id": usuario.id, "rol": usuario.rol}, minutos)
    return {
        "access_token": token,
        "token_type": "bearer",
        "rol": usuario.rol,
        "nombre_completo": usuario.nombre_completo,
        "debe_cambiar_password": usuario.debe_cambiar_password,
    }


@router.post("/cambiar-password", response_model=MensajeResponse, summary="Cambiar mi contraseña",
             description="Cualquier usuario autenticado. Exige la contraseña actual (o la temporal que te dio el administrador). "
                         "La nueva debe tener entre 8 y 64 caracteres y ser distinta de la actual.",
             responses={400: {"description": "La contraseña actual no coincide o la nueva es igual a la actual"}})
def cambiar_password(datos: CambioPassword, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    if not verificar_password(datos.password_actual, usuario.password_encriptada):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta.")
    if datos.password_nueva == datos.password_actual:
        raise HTTPException(status_code=400, detail="La contraseña nueva debe ser distinta de la actual.")
    usuario.password_encriptada = encriptar_password(datos.password_nueva)
    usuario.debe_cambiar_password = False
    auditar(db, usuario, "Cambió su contraseña", "Seguridad", usuario.id, None)
    db.commit()
    return {"mensaje": "Contraseña actualizada."}

@router.post("/aceptar-politica-datos", response_model=MensajeResponse, summary="Aceptar la política de tratamiento de datos",
             description="Roles: **todos**. Deja registrada la fecha en que la persona aceptó (Ley 1581 de 2012). Es idempotente.")
def aceptar_politica_datos(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    if usuario.politica_datos_fecha is None:
        usuario.politica_datos_fecha = ahora_utc()
        auditar(db, usuario, "Aceptó la política de datos", "Seguridad", usuario.id, None)
        db.commit()
    return {"mensaje": "Política de datos aceptada."}
