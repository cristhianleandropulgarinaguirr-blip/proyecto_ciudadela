# app/routers/auth.py
from datetime import timedelta

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import config, limitador, sesiones, totp
from app.auditoria import auditar
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db
from app.constantes import RolNombre
from app.dependencies import get_current_user, requiere_roles, sid_actual
from app import arrendamientos
from app.models import Arrendamiento, IntentoLogin, Sesion, Usuario, ahora_utc
from app.schemas.negocio import MensajeResponse
from app.schemas.seguridad import (DosPasosActivada, DosPasosCodigo, DosPasosConfirmar, DosPasosEstado, DosPasosIniciar, DosPasosInicio,
                                   MensajeSeguridad, ReauthRespuesta, Reautenticar)
from app.schemas.usuarios import CambioPassword, SesionResponse, TokenResponse
from app.security import HASH_FALSO, crear_token_acceso, crear_token_reauth, encriptar_password, es_hash_antiguo, verificar_password

router = APIRouter(prefix="/auth", tags=["Autenticación"])

MAX_FALLOS = 5            # intentos fallidos seguidos permitidos
BLOQUEO_MINUTOS = 15      # cuánto dura el bloqueo; también es la "memoria" del contador


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def _bloqueo_activo(db: Session, clave: str) -> None:
    """429 si ese correo está bloqueado por demasiados fallos."""
    ahora = ahora_utc()
    intento = db.query(IntentoLogin).filter(IntentoLogin.clave == clave).first()
    if intento and intento.bloqueado_hasta and intento.bloqueado_hasta > ahora:
        minutos = max(1, int((intento.bloqueado_hasta - ahora).total_seconds() // 60) + 1)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {minutos} min.",
                            headers={"Retry-After": str(minutos * 60)})


def _registrar_fallo(db: Session, request: Request, clave: str, usuario: Optional[Usuario]) -> None:
    """Cuenta un fallo (contraseña o código de dos pasos incorrectos) contra el correo y contra la IP. Tras 5 seguidos el correo se bloquea 15 min.
    Se cuenta por el correo escrito (exista o no), así tampoco se descubre qué cuentas existen mirando quién se bloquea."""
    ahora = ahora_utc()
    limitador.LOGIN_FALLOS_IP.registrar(_ip(request))
    intento = db.query(IntentoLogin).filter(IntentoLogin.clave == clave).first()
    if intento is None:
        intento = IntentoLogin(clave=clave, fallos=0)
        db.add(intento)
    if intento.ultimo_intento and intento.ultimo_intento < ahora - timedelta(minutes=BLOQUEO_MINUTOS):
        intento.fallos = 0                      # los fallos viejos no cuentan
    intento.fallos = (intento.fallos or 0) + 1
    intento.ultimo_intento = ahora
    if intento.fallos >= MAX_FALLOS:
        intento.bloqueado_hasta, intento.fallos = ahora + timedelta(minutes=BLOQUEO_MINUTOS), 0
        auditar(db, None, "Bloqueó inicio de sesión", "Seguridad", usuario.id if usuario else None,
                f"{MAX_FALLOS} intentos fallidos con «{clave[:80]}»; bloqueado {BLOQUEO_MINUTOS} min")
    db.commit()


def _segundo_factor_valido(db: Session, usuario: Usuario, codigo: str) -> bool:
    """Código de la app de autenticación (6 dígitos, un solo uso) o un código de recuperación (uso único). Modifica `usuario`: quien llama hace commit."""
    secreto = totp.descifrar(usuario.totp_secreto)
    if secreto:
        paso = totp.verificar(secreto, codigo, usuario.totp_ultimo_paso)
        if paso is not None:
            usuario.totp_ultimo_paso = paso
            return True
    quedan = totp.consumir_recuperacion(usuario.codigos_recuperacion, codigo)
    if quedan is not None:
        usuario.codigos_recuperacion = quedan
        auditar(db, usuario, "Usó un código de recuperación de dos pasos", "Seguridad", usuario.id, f"quedan {totp.quedan_recuperacion(quedan)}")
        return True
    return False


def _exigir_clave(db: Session, request: Request, usuario: Usuario, password: str) -> None:
    """Para acciones que piden la contraseña estando ya dentro (confirmar, activar o quitar los dos pasos): misma protección contra adivinarla.
    Responde 400 (nunca 401: la app web leería un 401 como «sesión vencida»)."""
    clave = usuario.email.strip().lower()
    _bloqueo_activo(db, clave)
    if not verificar_password(password, usuario.password_encriptada):
        _registrar_fallo(db, request, clave, usuario)
        raise HTTPException(status_code=400, detail="La contraseña no es correcta.")


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión y obtener el token JWT",
    description="Recibe `username` (el correo) y `password` como formulario. Devuelve un token JWT "
    "firmado que se envía en el encabezado `Authorization: Bearer <token>`. "
    "En Swagger usa el botón **Authorize** (candado) para probar las rutas protegidas. "
    "Las cuentas las crea el administrador en `POST /usuarios/`. "
    "Si la cuenta tiene la **verificación en dos pasos**, la primera llamada responde 401 con la cabecera `X-2FA-Requerida: 1`; "
    "repítela con el código en la cabecera `X-Codigo-2FA`.",
    responses={401: {"description": "Credenciales incorrectas o falta el código de dos pasos"}, 403: {"description": "Usuario desactivado"},
               429: {"description": "Demasiados intentos fallidos: espera unos minutos"}},
)
def login_usuario(request: Request, response: Response, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ahora = ahora_utc()
    clave = form.username.strip().lower()

    # Límite de intentos: tras 5 fallos seguidos ese correo queda bloqueado 15 minutos (y la IP tiene su propio tope).
    _bloqueo_activo(db, clave)
    if limitador.LOGIN_FALLOS_IP.agotada(_ip(request)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Demasiados intentos fallidos desde esta conexión. Intenta de nuevo en unos minutos.",
                            headers={"Retry-After": "600"})

    usuario = db.query(Usuario).filter(Usuario.email == form.username).first()

    # Mismo mensaje Y mismo tiempo para «no existe» y «clave incorrecta»: no revela qué correos están registrados (si no existe, se compara contra un hash falso).
    if usuario is None:
        verificar_password(form.password, HASH_FALSO)
        _registrar_fallo(db, request, clave, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas.", headers={"WWW-Authenticate": "Bearer"})
    if not verificar_password(form.password, usuario.password_encriptada):
        _registrar_fallo(db, request, clave, usuario)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas.", headers={"WWW-Authenticate": "Bearer"})
    if not usuario.esta_activo:
        if usuario.rol == "Inquilino" and db.query(Arrendamiento).filter(Arrendamiento.inquilino_id == usuario.id, Arrendamiento.estado == "Pendiente").first():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tu acceso está pendiente de aprobación por la administración.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado.")
    if usuario.rol == "Inquilino" and not arrendamientos.contrato_vigente(db, usuario):
        db.commit()    # contrato vencido: queda cerrado y la cuenta desactivada
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tu contrato de arrendamiento ya no está vigente. Habla con el propietario o con la administración.")

    # v5.3 · segundo paso. La contraseña ya es correcta: si falta el código, NO cuenta como fallo (es el flujo normal); si es incorrecto, sí.
    if usuario.totp_activo:
        codigo = request.headers.get("x-codigo-2fa", "").strip()
        if not codigo:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer", "X-2FA-Requerida": "1"},
                                detail="Escribe el código de 6 dígitos de tu app de autenticación.")
        if not _segundo_factor_valido(db, usuario, codigo):
            db.rollback()
            _registrar_fallo(db, request, clave, usuario)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer", "X-2FA-Requerida": "1"},
                                detail="Código incorrecto. Revisa que la hora de tu celular sea la automática, o usa un código de recuperación.")

    intento = db.query(IntentoLogin).filter(IntentoLogin.clave == clave).first()
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
                  ciudadela_rt: Optional[str] = Cookie(default=None, alias=sesiones.COOKIE)):
    sesiones.exigir_csrf(request)
    try:
        # v5.3: la app avisa (X-Actividad: 1) si la persona tocó la pantalla desde la última renovación; sin eso, la sesión del administrador no se alarga.
        sesion, nuevo, usuario = sesiones.renovar(db, ciudadela_rt, actividad=request.headers.get("x-actividad", "") == "1")
    except HTTPException:
        sesiones.quitar_cookie(response)
        raise
    return _emitir(db, request, response, usuario, sesion, nuevo)


@router.post("/logout", response_model=MensajeResponse, summary="Cerrar sesión en este dispositivo",
             description="Revoca la sesión de este dispositivo en el servidor (el token deja de servir al instante) y borra la cookie.")
def cerrar_sesion(request: Request, response: Response, db: Session = Depends(get_db), ciudadela_rt: Optional[str] = Cookie(default=None, alias=sesiones.COOKIE)):
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


# ====================================================================================================
#  v5.3 · Confirmar la contraseña (acciones sensibles) y verificación en dos pasos (TOTP)
# ====================================================================================================
@router.post("/reautenticar", response_model=ReauthRespuesta, summary="Confirmar mi contraseña para una acción sensible",
             description="Roles: **todos**. Devuelve un «pase» que dura pocos minutos (`REAUTH_MINUTOS`); se envía en la cabecera `X-Reauth` a las acciones sensibles "
                         "del administrador (crear o desactivar usuarios, restablecer claves, coeficientes, importar y exportar datos). La app web lo hace sola con una ventana emergente.",
             responses={400: {"description": "Contraseña incorrecta"}, 429: {"description": "Demasiados intentos"}})
def reautenticar(datos: Reautenticar, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user),
                 sid: Optional[str] = Depends(sid_actual)):
    _exigir_clave(db, request, usuario, datos.password)
    return {"reauth_token": crear_token_reauth(usuario.id, sid or ""), "expira_en": config.REAUTH_MINUTOS * 60}


solo_admin = requiere_roles(RolNombre.ADMINISTRADOR)


@router.get("/2fa/estado", response_model=DosPasosEstado, summary="¿Tengo la verificación en dos pasos activa?", description="Solo **Administrador**.")
def dos_pasos_estado(usuario: Usuario = Depends(solo_admin)):
    return {"activo": bool(usuario.totp_activo), "obligatorio": config.EXIGIR_2FA_ADMIN, "codigos_restantes": totp.quedan_recuperacion(usuario.codigos_recuperacion)}


@router.post("/2fa/iniciar", response_model=DosPasosInicio, summary="Empezar a activar la verificación en dos pasos",
             description="Solo **Administrador**. Exige la contraseña. Devuelve el secreto y un código QR para la app de autenticación; la verificación queda INACTIVA "
                         "hasta confirmar un código en `POST /auth/2fa/activar`.",
             responses={400: {"description": "Contraseña incorrecta o ya está activa"}})
def dos_pasos_iniciar(datos: DosPasosIniciar, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(solo_admin)):
    _exigir_clave(db, request, usuario, datos.password)
    if usuario.totp_activo:
        raise HTTPException(status_code=400, detail="La verificación en dos pasos ya está activa. Desactívala primero si quieres configurarla de nuevo.")
    from app import marca
    secreto = totp.nuevo_secreto()
    usuario.totp_secreto, usuario.totp_ultimo_paso = totp.cifrar(secreto), None
    db.commit()
    enlace = totp.uri(secreto, usuario.email, marca.nombre())
    return {"secreto": secreto, "uri": enlace, "qr": totp.qr_svg(enlace)}


@router.post("/2fa/activar", response_model=DosPasosActivada, summary="Confirmar un código y activar la verificación en dos pasos",
             description="Solo **Administrador**. Envía el código de 6 dígitos que muestra tu app. Devuelve los **códigos de recuperación** (se muestran una sola vez). "
                         "Cierra tus sesiones en otros dispositivos.",
             responses={400: {"description": "Código incorrecto o no se inició la activación"}})
def dos_pasos_activar(datos: DosPasosCodigo, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(solo_admin),
                      sid: Optional[str] = Depends(sid_actual)):
    clave = usuario.email.strip().lower()
    _bloqueo_activo(db, clave)
    secreto = totp.descifrar(usuario.totp_secreto)
    if usuario.totp_activo or not secreto:
        raise HTTPException(status_code=400, detail="Primero inicia la activación (paso del código QR).")
    paso = totp.verificar(secreto, datos.codigo, usuario.totp_ultimo_paso)
    if paso is None:
        _registrar_fallo(db, request, clave, usuario)
        raise HTTPException(status_code=400, detail="Ese código no coincide. Revisa que la hora de tu celular sea la automática e inténtalo con el código nuevo.")
    claros, guardados = totp.generar_recuperacion()
    usuario.totp_activo, usuario.totp_ultimo_paso, usuario.codigos_recuperacion = True, paso, guardados
    otras = sesiones.revocar_todas(db, usuario.id, excepto=sid)
    auditar(db, usuario, "Activó la verificación en dos pasos", "Seguridad", usuario.id, f"cerró {otras} sesión(es) en otros dispositivos" if otras else None)
    db.commit()
    return {"mensaje": "Verificación en dos pasos activada.", "codigos_recuperacion": claros}


def _confirmar_con_codigo(db: Session, request: Request, usuario: Usuario, datos: DosPasosConfirmar) -> None:
    """Contraseña + código vigente: lo que se exige para desactivar o regenerar los códigos."""
    _exigir_clave(db, request, usuario, datos.password)
    if not usuario.totp_activo:
        raise HTTPException(status_code=400, detail="La verificación en dos pasos no está activa.")
    if not _segundo_factor_valido(db, usuario, datos.codigo):
        db.rollback()
        _registrar_fallo(db, request, usuario.email.strip().lower(), usuario)
        raise HTTPException(status_code=400, detail="Código incorrecto. Si acabas de usar uno, espera al siguiente (cambia cada 30 segundos).")


@router.post("/2fa/desactivar", response_model=MensajeSeguridad, summary="Desactivar la verificación en dos pasos",
             description="Solo **Administrador**. Exige la contraseña y un código vigente (o de recuperación).", responses={400: {"description": "Contraseña o código incorrectos"}})
def dos_pasos_desactivar(datos: DosPasosConfirmar, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(solo_admin),
                         sid: Optional[str] = Depends(sid_actual)):
    if config.EXIGIR_2FA_ADMIN:
        raise HTTPException(status_code=400, detail="La administración del conjunto exige la verificación en dos pasos: no se puede desactivar.")
    _confirmar_con_codigo(db, request, usuario, datos)
    usuario.totp_activo, usuario.totp_secreto, usuario.totp_ultimo_paso, usuario.codigos_recuperacion = False, None, None, None
    sesiones.revocar_todas(db, usuario.id, excepto=sid)
    auditar(db, usuario, "Desactivó la verificación en dos pasos", "Seguridad", usuario.id, None)
    db.commit()
    return {"mensaje": "Verificación en dos pasos desactivada."}


@router.post("/2fa/codigos-nuevos", response_model=DosPasosActivada, summary="Generar códigos de recuperación nuevos",
             description="Solo **Administrador**. Exige la contraseña y un código vigente. Los códigos anteriores dejan de servir.", responses={400: {"description": "Contraseña o código incorrectos"}})
def dos_pasos_codigos_nuevos(datos: DosPasosConfirmar, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(solo_admin)):
    _confirmar_con_codigo(db, request, usuario, datos)
    claros, guardados = totp.generar_recuperacion()
    usuario.codigos_recuperacion = guardados
    auditar(db, usuario, "Generó códigos de recuperación nuevos", "Seguridad", usuario.id, None)
    db.commit()
    return {"mensaje": "Códigos nuevos generados. Los anteriores ya no sirven.", "codigos_recuperacion": claros}
