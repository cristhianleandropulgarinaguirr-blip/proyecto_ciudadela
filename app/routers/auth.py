# app/routers/auth.py
from datetime import timedelta

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import sesiones
from app.auditoria import auditar
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db
from app.dependencies import get_current_user, sid_actual
from app import arrendamientos
from app.models import Arrendamiento, IntentoLogin, Sesion, Usuario, ahora_utc
from app.schemas.negocio import MensajeResponse
from app.schemas.usuarios import CambioPassword, SesionResponse, TokenResponse
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
def login_usuario(request: Request, response: Response, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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
        if usuario.rol == "Inquilino" and db.query(Arrendamiento).filter(Arrendamiento.inquilino_id == usuario.id, Arrendamiento.estado == "Pendiente").first():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tu acceso está pendiente de aprobación por la administración.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado.")
    if usuario.rol == "Inquilino" and not arrendamientos.contrato_vigente(db, usuario):
        db.commit()    # contrato vencido: queda cerrado y la cuenta desactivada
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tu contrato de arrendamiento ya no está vigente. Habla con el propietario o con la administración.")
    if intento:                                     # entró bien: el contador vuelve a cero
        db.delete(intento)
        db.commit()

    # Migración transparente: si la clave estaba con el SHA-256 antiguo, se pasa a bcrypt.
    if es_hash_antiguo(usuario.password_encriptada):
        usuario.password_encriptada = encriptar_password(form.password)
        db.commit()

    return _emitir(db, request, response, usuario)


def _emitir(db: Session, request: Request, response: Response, usuario: Usuario, sesion: Optional[Sesion] = None,
            refresh: Optional[str] = None) -> dict:
    """Crea la sesión (o reutiliza la que ya se renovó), pone la cookie de renovación y devuelve el access token."""
    if sesion is None:
        sesion, refresh = sesiones.crear_sesion(db, usuario, request)
        db.commit()
    elif refresh is not None:
        db.commit()
    if refresh is not None:
        sesiones.poner_cookie(response, request, refresh, sesion)
    token = crear_token_acceso({"sub": usuario.email, "usuario_id": usuario.id, "rol": usuario.rol, "sid": sesion.id})
    response.headers["Cache-Control"] = "no-store"
    return {
        "access_token": token,
        "token_type": "bearer",
        "rol": usuario.rol,
        "nombre_completo": usuario.nombre_completo,
        "debe_cambiar_password": usuario.debe_cambiar_password,
        "expira_en": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/refresh", response_model=TokenResponse, summary="Renovar el token de acceso",
             description="Usa la cookie de renovación (HttpOnly) para entregar un token de acceso nuevo y rotar la cookie. "
                         "Lo llama la app sola; exige el encabezado `X-Requested-With: ciudadela`.",
             responses={401: {"description": "No hay sesión, expiró o fue cerrada"}, 403: {"description": "Falta el encabezado de la app"}})
def renovar_token(request: Request, response: Response, db: Session = Depends(get_db),
                  ciudadela_rt: Optional[str] = Cookie(default=None)):
    sesiones.exigir_csrf(request)
    try:
        sesion, nuevo, usuario = sesiones.renovar(db, ciudadela_rt)
    except HTTPException:
        sesiones.quitar_cookie(response)
        raise
    return _emitir(db, request, response, usuario, sesion, nuevo)


@router.post("/logout", response_model=MensajeResponse, summary="Cerrar sesión en este dispositivo",
             description="Revoca la sesión de este dispositivo en el servidor (el token deja de servir al instante) y borra la cookie.")
def cerrar_sesion(request: Request, response: Response, db: Session = Depends(get_db), ciudadela_rt: Optional[str] = Cookie(default=None)):
    sesiones.exigir_csrf(request)
    if ciudadela_rt:
        from app.security import hash_token
        s = db.query(Sesion).filter(Sesion.token_hash == hash_token(ciudadela_rt)).first()
        if s is not None:
            sesiones.revocar(db, s.id)
            db.commit()
    sesiones.quitar_cookie(response)
    return {"mensaje": "Sesión cerrada."}


@router.get("/sesiones", response_model=list[SesionResponse], summary="Dispositivos con mi sesión abierta",
            description="Roles: **todos**. Sirve para revisar desde dónde entró tu cuenta y cerrar lo que no reconozcas.")
def mis_sesiones(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user), sid: Optional[str] = Depends(sid_actual)):
    ahora = ahora_utc()
    filas = (db.query(Sesion).filter(Sesion.usuario_id == usuario.id, Sesion.revocada.is_(None), Sesion.maxima > ahora, Sesion.expira > ahora)
             .order_by(Sesion.ultimo_uso.desc()).all())
    return [SesionResponse(id=s.id, dispositivo=s.dispositivo, ip=s.ip, creada=s.creada, ultimo_uso=s.ultimo_uso, actual=s.id == sid) for s in filas]


@router.delete("/sesiones/{sesion_id}", response_model=MensajeResponse, summary="Cerrar la sesión de otro dispositivo",
               responses={404: {"description": "Sesión no encontrada"}})
def cerrar_otra_sesion(sesion_id: str, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    s = db.get(Sesion, sesion_id)
    if s is None or s.usuario_id != usuario.id:          # no revelamos si existe una de otra persona
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")
    sesiones.revocar(db, s.id)
    auditar(db, usuario, "Cerró una sesión", "Seguridad", usuario.id, s.dispositivo)
    db.commit()
    return {"mensaje": "Sesión cerrada."}


@router.post("/cerrar-otras-sesiones", response_model=MensajeResponse, summary="Cerrar la sesión en todos los demás dispositivos",
             description="Deja abierta solo la sesión de este dispositivo.")
def cerrar_otras(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user), sid: Optional[str] = Depends(sid_actual)):
    n = sesiones.revocar_todas(db, usuario.id, excepto=sid)
    auditar(db, usuario, "Cerró las demás sesiones", "Seguridad", usuario.id, f"{n} sesión(es)")
    db.commit()
    return {"mensaje": f"Se cerraron {n} sesión(es) en otros dispositivos."}


@router.post("/cambiar-password", response_model=MensajeResponse, summary="Cambiar mi contraseña",
             description="Cualquier usuario autenticado. Exige la contraseña actual (o la temporal que te dio el administrador). "
                         "La nueva debe tener entre 8 y 64 caracteres y ser distinta de la actual.",
             responses={400: {"description": "La contraseña actual no coincide o la nueva es igual a la actual"}})
def cambiar_password(datos: CambioPassword, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user),
                    sid: Optional[str] = Depends(sid_actual)):
    if not verificar_password(datos.password_actual, usuario.password_encriptada):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta.")
    if datos.password_nueva == datos.password_actual:
        raise HTTPException(status_code=400, detail="La contraseña nueva debe ser distinta de la actual.")
    usuario.password_encriptada = encriptar_password(datos.password_nueva)
    usuario.debe_cambiar_password = False
    otras = sesiones.revocar_todas(db, usuario.id, excepto=sid)      # si alguien más tenía tu sesión, deja de tenerla
    auditar(db, usuario, "Cambió su contraseña", "Seguridad", usuario.id, f"cerró {otras} sesión(es) en otros dispositivos" if otras else None)
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
