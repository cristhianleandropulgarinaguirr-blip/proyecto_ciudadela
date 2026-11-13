# app/sesiones.py
# Sesiones seguras (versión 3.1).
#  - Access token (JWT, 15 min): va en el encabezado Authorization y lleva el id de sesión («sid»).
#  - Refresh token (opaco, cookie HttpOnly + SameSite=Strict, ruta /auth): renueva el access token. Se ROTA en cada uso.
#    En la base de datos solo queda su hash SHA-256 (si la base se filtra, los tokens no sirven).
#  - Si alguien presenta un refresh token que ya fue reemplazado (robo), se revoca toda la sesión.
#  - «Cerrar sesión», cambiar la contraseña, desactivar o restablecer a un usuario revocan sesiones al instante.
import logging
import time
from datetime import timedelta
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app import config
from app.auditoria import auditar
from app.constantes import RolNombre
from app.models import Sesion, Usuario, ahora_utc
from app.security import hash_token, nuevo_token_renovacion

logger = logging.getLogger("conjunto")

COOKIE = "ciudadela_rt"
RUTA_COOKIE = "/auth"
ENCABEZADO_CSRF = "x-requested-with"
VALOR_CSRF = "ciudadela"
GRACIA_ROTACION_S = 20        # dos pestañas pueden renovar a la vez: el token recién reemplazado se tolera unos segundos
MAX_SESIONES_POR_USUARIO = 20


def vida_sesion(usuario: Usuario) -> tuple[timedelta, timedelta]:
    """(vida deslizante, vida máxima absoluta) según el rol."""
    if usuario.rol == RolNombre.GUARDIA.value:
        return timedelta(hours=config.GUARDIA_TOKEN_HORAS), timedelta(hours=max(24, config.GUARDIA_TOKEN_HORAS))
    dias = config.SESION_DIAS_ADMIN if usuario.rol == RolNombre.ADMINISTRADOR.value else config.SESION_DIAS
    return timedelta(days=dias), timedelta(days=max(dias, config.SESION_MAXIMA_DIAS))


# ---------------------------------------------------------------- validez rápida (caché de 15 s)
# get_current_user consulta la sesión en CADA petición. Un caché mínimo en memoria evita esa consulta casi siempre;
# revocar invalida la entrada al instante en este proceso y, en otro, el máximo desfase es TTL_S.
TTL_S = 15
_cache: dict[str, tuple[float, bool]] = {}


def invalidar_cache(sid: Optional[str] = None) -> None:
    _cache.pop(sid, None) if sid else _cache.clear()


def sesion_valida(db: Session, sid: str, usuario_id: int) -> bool:
    ahora = time.monotonic()
    previo = _cache.get(sid)
    if previo and previo[0] > ahora:
        return previo[1]
    s = db.get(Sesion, sid)
    ok = bool(s and s.usuario_id == usuario_id and s.revocada is None and s.maxima > ahora_utc())
    if len(_cache) > 5000:
        _cache.clear()
    _cache[sid] = (ahora + TTL_S, ok)
    return ok


# ---------------------------------------------------------------- utilidades de petición
def es_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def describir_dispositivo(ua: str) -> str:
    u = (ua or "").lower()
    so = next((n for k, n in (("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"), ("windows", "Windows"),
                              ("mac os", "Mac"), ("linux", "Linux")) if k in u), "Dispositivo")
    nav = next((n for k, n in (("edg/", "Edge"), ("opr/", "Opera"), ("samsungbrowser", "Samsung Internet"), ("firefox", "Firefox"),
                               ("chrome", "Chrome"), ("safari", "Safari")) if k in u), "navegador")
    return f"{so} · {nav}"


def _ip(request: Request) -> Optional[str]:
    return (request.client.host if request.client else None)


def exigir_csrf(request: Request) -> None:
    """La cookie de renovación solo se usa desde nuestra propia app: exige un encabezado que un sitio ajeno no puede enviar."""
    if request.headers.get(ENCABEZADO_CSRF, "").lower() != VALOR_CSRF:
        raise HTTPException(status_code=403, detail="Solicitud no permitida.")


def poner_cookie(response: Response, request: Request, token: str, sesion: Sesion) -> None:
    restante = max(60, int((sesion.expira - ahora_utc()).total_seconds()))
    response.set_cookie(COOKIE, token, max_age=restante, httponly=True, samesite="strict",
                        secure=es_https(request), path=RUTA_COOKIE)


def quitar_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path=RUTA_COOKIE)


# ---------------------------------------------------------------- ciclo de vida
def limpiar_viejas(db: Session) -> None:
    """Borra sesiones vencidas o revocadas hace tiempo (se llama al iniciar sesión; es barato)."""
    corte = ahora_utc() - timedelta(days=7)
    db.query(Sesion).filter((Sesion.maxima < ahora_utc()) | (Sesion.revocada < corte)).delete(synchronize_session=False)


def crear_sesion(db: Session, usuario: Usuario, request: Request) -> tuple[Sesion, str]:
    desliza, maxima = vida_sesion(usuario)
    ahora = ahora_utc()
    token = nuevo_token_renovacion()
    sesion = Sesion(id=uuid4().hex, usuario_id=usuario.id, token_hash=hash_token(token), creada=ahora, ultimo_uso=ahora,
                    expira=ahora + desliza, maxima=ahora + maxima,
                    dispositivo=describir_dispositivo(request.headers.get("user-agent", "")), ip=_ip(request))
    db.add(sesion)
    # Tope de dispositivos: si hay demasiados, se cierran los más antiguos.
    activas = (db.query(Sesion).filter(Sesion.usuario_id == usuario.id, Sesion.revocada.is_(None), Sesion.maxima > ahora)
               .order_by(Sesion.ultimo_uso.desc()).all())
    for vieja in activas[MAX_SESIONES_POR_USUARIO - 1:]:
        vieja.revocada = ahora
        invalidar_cache(vieja.id)
    limpiar_viejas(db)
    return sesion, token


def _no_autorizado(detalle: str = "Tu sesión ya no es válida. Inicia sesión de nuevo.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detalle)


def renovar(db: Session, token: Optional[str]) -> tuple[Sesion, Optional[str], Usuario]:
    """Cambia un refresh token por otro nuevo. Devuelve (sesión, token_nuevo | None, usuario).
    token_nuevo es None cuando la petición llegó dentro de la gracia de rotación (otra pestaña ya renovó): se emite solo el access token."""
    if not token:
        raise _no_autorizado()
    h = hash_token(token)
    ahora = ahora_utc()
    s = db.query(Sesion).filter(Sesion.token_hash == h).first()
    if s is None:
        # ¿Es un token ya reemplazado? Entonces alguien lo está reutilizando.
        vieja = db.query(Sesion).filter(Sesion.token_anterior_hash == h).first()
        if vieja is not None and vieja.revocada is None:
            if vieja.rotado_en and (ahora - vieja.rotado_en).total_seconds() <= GRACIA_ROTACION_S:
                u = db.get(Usuario, vieja.usuario_id)
                if u is None or not u.esta_activo:
                    raise _no_autorizado()
                return vieja, None, u
            vieja.revocada = ahora
            invalidar_cache(vieja.id)
            auditar(db, None, "Sesión revocada por reutilización de token", "Seguridad", vieja.usuario_id,
                    f"{vieja.dispositivo or 'dispositivo'} · {vieja.ip or ''}")
            db.commit()
        raise _no_autorizado()
    if s.revocada is not None or s.expira <= ahora or s.maxima <= ahora:
        raise _no_autorizado("Tu sesión expiró. Inicia sesión de nuevo.")
    u = db.get(Usuario, s.usuario_id)
    if u is None or not u.esta_activo:
        raise _no_autorizado()
    desliza, _ = vida_sesion(u)
    nuevo = nuevo_token_renovacion()
    s.token_anterior_hash, s.token_hash, s.rotado_en = s.token_hash, hash_token(nuevo), ahora
    s.ultimo_uso = ahora
    s.expira = min(ahora + desliza, s.maxima)
    return s, nuevo, u


def revocar(db: Session, sid: Optional[str]) -> None:
    if not sid:
        return
    s = db.get(Sesion, sid)
    if s is not None and s.revocada is None:
        s.revocada = ahora_utc()
    invalidar_cache(sid)


def revocar_todas(db: Session, usuario_id: int, excepto: Optional[str] = None) -> int:
    ahora = ahora_utc()
    q = db.query(Sesion).filter(Sesion.usuario_id == usuario_id, Sesion.revocada.is_(None))
    if excepto:
        q = q.filter(Sesion.id != excepto)
    n = 0
    for s in q.all():
        s.revocada = ahora
        invalidar_cache(s.id)
        n += 1
    return n
