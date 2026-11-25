# app/routers/tecnico.py
# v5.6 · Rol «Mantenimiento»: un técnico SIN cuenta atiende UN reporte de daño desde un enlace temporal (/tecnico/<token>).
#
# Por qué un enlace y no una cuenta: el técnico entra una o dos veces, desde su celular, y no debe ver nada del conjunto. Una cuenta
# traería contraseña, 2FA, listas, permisos que revisar… y mucha más superficie de ataque. El enlace hace lo mismo con casi nada:
#   · Atado a UN solo reporte, vence pronto (por defecto 72 h, máximo 7 días) y el administrador lo puede anular al instante.
#     Un reporte tiene un solo enlace vigente: crear uno nuevo anula el anterior (si lo reenvían, el viejo deja de servir).
#   · La página muestra solo lo mínimo: apartamento, título, descripción y foto del daño. Nunca el nombre, el correo ni el teléfono
#     del residente (esos datos ni siquiera viajan en la respuesta).
#   · El técnico solo puede pasar el estado a «En reparación» o «Solucionado», con una nota y una foto de evidencia
#     (la foto es obligatoria para «Solucionado»). No puede reabrir, ni volver atrás, ni tocar otro reporte.
#   · Cada cambio queda en la auditoría y avisa al residente (y al propietario si quien reportó es inquilino) y al administrador.
#   · Cuando el técnico marca «Solucionado» el enlace se cierra solo.
#
# Riesgo que se acepta y se cuida: quien reciba el enlace puede reenviarlo. Por eso es de un solo reporte, caduca pronto, expone
# casi nada y el administrador puede anularlo. Esta es (con el pase de visitante) la otra parte de la API que se usa sin sesión:
# va aparte y bien limitada (app/limitador.py).
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from starlette.datastructures import UploadFile as ArchivoSubido
from sqlalchemy.orm import Session

from app import arrendamientos as reglas_arr, config, limitador, marca
from app.archivos import borrar_imagen, guardar_imagen_validada, leer_imagen
from app.auditoria import auditar
from app.constantes import EstadoDanio, EstadoEnlaceTecnico, EstadoTecnico, RolNombre
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import EnlaceTecnico, EvidenciaDanio, ReporteDanio, Usuario, ahora_utc
from app.notificaciones import notificar
from app.routers.publico import CABECERAS_API, CABECERAS_PAGINA as _CABECERAS_PASE
from app.schemas.tecnico import EnlaceTecnicoCrear, EnlaceTecnicoResponse

TAG_ADMIN = "Gestión de Incidencias y Daños"
TAG_PUBLICO = "Enlace de técnico (sin sesión)"
router = APIRouter()
ADMIN = RolNombre.ADMINISTRADOR

FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend"
PAGINA = FRONTEND / "tecnico" / "tecnico.html"
# La página solo carga SU css y SU js (mismo origen) y consulta SU api. `blob:` únicamente para mostrar la vista previa de la foto que el técnico acaba de elegir.
CSP_TECNICO = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; base-uri 'none'; "
               "form-action 'none'; frame-ancestors 'none'")
CABECERAS_PAGINA = {**_CABECERAS_PASE, "Content-Security-Policy": CSP_TECNICO}
CABECERAS_FOTO = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"}

MAX_NOTA = 500
MIN_NOTA_SOLUCIONADO = 5
MARGEN_MULTIPART_MB = 1          # el formulario trae la foto (máx. MAX_UPLOAD_MB) más unos pocos campos de texto


# ------------------------------------------------------------------ reglas (las usan el administrador y la página pública)
def _estado_enlace(e: EnlaceTecnico, reporte: Optional[ReporteDanio], ahora=None) -> str:
    """Vigente | Vencido | Revocado | Cerrado. Se calcula cada vez: nunca hay un «estado guardado» que pueda quedar desactualizado."""
    ahora = ahora or ahora_utc()
    if e.revocado_en is not None:
        return EstadoEnlaceTecnico.REVOCADO.value
    if e.cerrado_en is not None or (reporte is not None and reporte.estado == EstadoDanio.SOLUCIONADO.value):
        return EstadoEnlaceTecnico.CERRADO.value
    if e.valido_hasta <= ahora:
        return EstadoEnlaceTecnico.VENCIDO.value
    return EstadoEnlaceTecnico.VIGENTE.value


def _permitidos(estado_reporte: str) -> list[str]:
    """A qué estados puede pasar el técnico desde el estado actual. Solo hacia adelante: no hay vuelta atrás ni reapertura."""
    if estado_reporte in (EstadoDanio.ABIERTO.value, EstadoDanio.EN_REVISION.value):
        return [EstadoTecnico.EN_REPARACION.value, EstadoTecnico.SOLUCIONADO.value]
    if estado_reporte == EstadoDanio.EN_REPARACION.value:
        return [EstadoTecnico.SOLUCIONADO.value]
    return []


def _vista_admin(e: EnlaceTecnico, reporte: Optional[ReporteDanio]) -> EnlaceTecnicoResponse:
    estado = _estado_enlace(e, reporte)
    return EnlaceTecnicoResponse(id=e.id, reporte_id=e.reporte_id, estado=estado, etiqueta=e.etiqueta, valido_hasta=e.valido_hasta,
                                 fecha_creacion=e.fecha_creacion, ultimo_uso=e.ultimo_uso,
                                 enlace=f"/tecnico/{e.token}" if estado == EstadoEnlaceTecnico.VIGENTE.value else None)


# ------------------------------------------------------------------ administrador: crear, listar y anular enlaces
@router.post("/mantenimiento/danios/{reporte_id}/enlace-tecnico", response_model=EnlaceTecnicoResponse, status_code=201, tags=[TAG_ADMIN],
             summary="Crear el enlace de un técnico para un reporte",
             description="Solo **Administrador**. Genera un enlace temporal atado a ESTE reporte (por defecto 72 h, máximo 168 h). "
                         "Si el reporte ya tenía un enlace vigente, ese se anula: solo uno sirve a la vez. "
                         "El técnico lo abre sin iniciar sesión y solo ve apartamento, título, descripción y foto del daño.",
             responses={400: {"description": "El reporte ya está solucionado"}, 404: {"description": "Reporte no encontrado"}})
def crear_enlace(reporte_id: int, datos: EnlaceTecnicoCrear, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    reporte = db.get(ReporteDanio, reporte_id)
    if reporte is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    if reporte.estado == EstadoDanio.SOLUCIONADO.value:
        raise HTTPException(status_code=400, detail="Este reporte ya está solucionado: no hace falta un enlace de técnico.")
    ahora = ahora_utc()
    previos = (db.query(EnlaceTecnico).filter(EnlaceTecnico.reporte_id == reporte.id, EnlaceTecnico.revocado_en.is_(None),
                                              EnlaceTecnico.cerrado_en.is_(None), EnlaceTecnico.valido_hasta > ahora).all())
    for p in previos:
        p.revocado_en, p.revocado_por = ahora, admin.id          # un solo enlace vigente por reporte
    etiqueta = (datos.etiqueta or "").strip() or None
    nuevo = EnlaceTecnico(reporte_id=reporte.id, token=secrets.token_urlsafe(24), creado_por=admin.id, etiqueta=etiqueta,   # 192 bits: imposible de adivinar
                          valido_hasta=ahora + timedelta(hours=datos.horas), fecha_creacion=ahora)
    db.add(nuevo)
    db.flush()          # para conocer su número y dejarlo en la auditoría
    auditar(db, admin, "Creó enlace de técnico", "Daño", reporte.id,
            f"{reporte.titulo} · enlace #{nuevo.id} · {datos.horas} h" + (f" · {etiqueta}" if etiqueta else "") + (f" · anuló {len(previos)} anterior(es)" if previos else ""))
    db.commit()
    db.refresh(nuevo)
    return _vista_admin(nuevo, reporte)


@router.get("/mantenimiento/danios/{reporte_id}/enlaces-tecnico", response_model=list[EnlaceTecnicoResponse], tags=[TAG_ADMIN],
            summary="Ver los enlaces de técnico de un reporte",
            description="Solo **Administrador**. Del más nuevo al más viejo. La ruta del enlace (`enlace`) solo viene mientras el enlace está Vigente.",
            responses={404: {"description": "Reporte no encontrado"}})
def listar_enlaces(reporte_id: int, db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(ADMIN))):
    reporte = db.get(ReporteDanio, reporte_id)
    if reporte is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    enlaces = db.query(EnlaceTecnico).filter(EnlaceTecnico.reporte_id == reporte.id).order_by(EnlaceTecnico.id.desc()).limit(20).all()
    return [_vista_admin(e, reporte) for e in enlaces]


@router.post("/mantenimiento/enlaces-tecnico/{enlace_id}/revocar", response_model=EnlaceTecnicoResponse, tags=[TAG_ADMIN],
             summary="Anular un enlace de técnico",
             description="Solo **Administrador**. Desde ese momento el enlace deja de servir (la página y la foto responden «ya no está activo»).",
             responses={400: {"description": "El enlace ya no estaba vigente"}, 404: {"description": "Enlace no encontrado"}})
def revocar_enlace(enlace_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    e = db.get(EnlaceTecnico, enlace_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Enlace no encontrado.")
    reporte = db.get(ReporteDanio, e.reporte_id)
    if _estado_enlace(e, reporte) != EstadoEnlaceTecnico.VIGENTE.value:
        raise HTTPException(status_code=400, detail="Este enlace ya no estaba vigente: venció, ya fue anulado o el trabajo se cerró.")
    e.revocado_en, e.revocado_por = ahora_utc(), admin.id
    auditar(db, admin, "Anuló enlace de técnico", "Daño", e.reporte_id, f"{reporte.titulo if reporte else ''} · enlace #{e.id}" + (f" · {e.etiqueta}" if e.etiqueta else ""))
    db.commit()
    db.refresh(e)
    return _vista_admin(e, reporte)


@router.get("/mantenimiento/danios/{reporte_id}/evidencias/{evidencia_id}/foto", tags=[TAG_ADMIN], summary="Descargar la foto de evidencia del técnico",
            description="Solo quien hizo el reporte o un **Administrador** (igual que la foto del daño). Las fotos NO son públicas.",
            responses={404: {"description": "Evidencia o foto no encontradas"}, 403: {"description": "No es tu reporte"}})
def ver_foto_evidencia(reporte_id: int, evidencia_id: int, miniatura: bool = False, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    ev = db.get(EvidenciaDanio, evidencia_id)
    if ev is None or ev.reporte_id != reporte_id:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada.")
    reporte = db.get(ReporteDanio, reporte_id)
    if reporte is None or (reporte.usuario_id != usuario.id and usuario.rol != ADMIN.value):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver esta foto.")
    imagen = leer_imagen(ev.foto, miniatura=miniatura) if ev.foto else None
    if imagen is None:
        raise HTTPException(status_code=404, detail="Esta actualización no tiene foto.")
    return Response(content=imagen[0], media_type=imagen[1], headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})


# ------------------------------------------------------------------ página pública del técnico (sin sesión)
def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def _limitar(ventana: limitador.Ventana, clave) -> None:
    if not ventana.intentar(clave):
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Espera unos minutos e inténtalo de nuevo.")


def _enlace_o_404(db: Session, token: str) -> EnlaceTecnico:
    e = db.query(EnlaceTecnico).filter(EnlaceTecnico.token == token).first()
    if e is None:
        raise HTTPException(status_code=404, detail="Este enlace no es válido.")
    return e


@router.get("/tecnico/{token}", response_class=HTMLResponse, include_in_schema=False)
def pagina_del_tecnico(token: str):
    """La página en sí es siempre la misma; ella pide sus datos a /tecnico-publico/<token>. Un token malo muestra «enlace no válido» ahí."""
    return HTMLResponse(marca.aplicar_a_html(PAGINA.read_text(encoding="utf-8")), headers=CABECERAS_PAGINA)


@router.get("/tecnico-publico/{token}", tags=[TAG_PUBLICO], summary="Datos mínimos del reporte para la página del técnico",
            description="**Sin sesión.** El token del enlace es la única llave. Mientras el enlace esté vigente devuelve SOLO: apartamento, título, descripción, "
                        "si hay foto, el estado actual y lo que el técnico ya dejó. **Nunca** el nombre, el correo ni el teléfono del residente. "
                        "Si el enlace venció, se anuló o se cerró, no devuelve ningún dato del reporte. Límite: 90 consultas por minuto por IP.",
            responses={404: {"description": "Enlace no válido"}, 429: {"description": "Demasiadas solicitudes"}})
def datos_para_el_tecnico(token: str, request: Request, response: Response, db: Session = Depends(get_db)):
    _limitar(limitador.LECTURAS_PUBLICAS, _ip(request))
    e = _enlace_o_404(db, token)
    reporte = db.get(ReporteDanio, e.reporte_id)
    estado = _estado_enlace(e, reporte)
    response.headers.update(CABECERAS_API)
    salida = {"conjunto": {"nombre": config.CONJUNTO_NOMBRE},
              "enlace": {"estado": estado, "sirve": estado == EstadoEnlaceTecnico.VIGENTE.value, "valido_hasta": e.valido_hasta},
              "reporte": None}
    if reporte is None or estado != EstadoEnlaceTecnico.VIGENTE.value:
        return salida          # vencido, anulado o cerrado: ni un dato del reporte
    residente = db.get(Usuario, reporte.usuario_id)
    salida["reporte"] = {
        "titulo": reporte.titulo, "descripcion": reporte.descripcion,
        "apartamento": (residente.apartamento if residente else None) or "Zonas comunes",      # lo único del residente que se muestra
        "estado": reporte.estado, "reportado": reporte.fecha_creacion,
        "tiene_foto": bool(reporte.foto_url and reporte.foto_url != "sin_foto.jpg"),
        "estados_permitidos": _permitidos(reporte.estado),
        "evidencias": [{"estado": ev.estado, "nota": ev.nota, "fecha": ev.fecha, "tiene_foto": ev.tiene_foto} for ev in reporte.evidencias],
    }
    return salida


@router.get("/tecnico-publico/{token}/foto", tags=[TAG_PUBLICO], summary="Foto del daño para la página del técnico", response_class=Response,
            description="**Sin sesión.** Solo mientras el enlace esté vigente. Las fotos se guardan sin ubicación GPS.",
            responses={200: {"content": {"image/jpeg": {}}}, 404: {"description": "Enlace no válido, ya no activo o reporte sin foto"}, 429: {"description": "Demasiadas solicitudes"}})
def foto_para_el_tecnico(token: str, request: Request, miniatura: bool = Query(False), db: Session = Depends(get_db)):
    _limitar(limitador.LECTURAS_PUBLICAS, _ip(request))
    e = _enlace_o_404(db, token)
    reporte = db.get(ReporteDanio, e.reporte_id)
    if reporte is None or _estado_enlace(e, reporte) != EstadoEnlaceTecnico.VIGENTE.value or not reporte.foto_url or reporte.foto_url == "sin_foto.jpg":
        raise HTTPException(status_code=404, detail="No hay foto disponible.")
    imagen = leer_imagen(reporte.foto_url, miniatura=miniatura)
    if imagen is None:
        raise HTTPException(status_code=404, detail="No hay foto disponible.")
    return Response(content=imagen[0], media_type=imagen[1], headers=CABECERAS_FOTO)


def _nota_limpia(texto) -> str:
    """Sin caracteres de control (se conservan los saltos de línea), recortada y limitada a 500 caracteres."""
    return "".join(c for c in str(texto or "") if c.isprintable() or c == "\n").strip()[:MAX_NOTA]


_ESQUEMA_ESTADO = {"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
    "type": "object", "required": ["nuevo_estado"],
    "properties": {"nuevo_estado": {"type": "string", "enum": [e.value for e in EstadoTecnico]},
                   "nota": {"type": "string", "maxLength": MAX_NOTA, "description": "Obligatoria al pasar a Solucionado (mínimo 5 caracteres)"},
                   "archivo_foto": {"type": "string", "format": "binary", "description": "Foto de evidencia JPG, PNG o WEBP (máx. 5 MB). Obligatoria al pasar a Solucionado"}}}}}}}


@router.post("/tecnico-publico/{token}/estado", tags=[TAG_PUBLICO], summary="El técnico cambia el estado, con nota y foto de evidencia",
             openapi_extra=_ESQUEMA_ESTADO,
             description="**Sin sesión.** Solo con el enlace vigente. Pasa el reporte a **En Reparacion** o **Solucionado** (nunca hacia atrás). "
                         "Para Solucionado la nota (5+ caracteres) y la foto son obligatorias; el enlace se cierra solo. Queda en la auditoría y avisa al residente. "
                         "Límites: 10 intentos cada 10 minutos por IP y 12 por hora por enlace. Se envía como `multipart/form-data`.",
             responses={400: {"description": "Enlace ya no activo, cambio no permitido, o falta la nota o la foto"}, 404: {"description": "Enlace no válido"},
                        413: {"description": "Foto demasiado grande"}, 422: {"description": "Estado no permitido para el técnico"}, 429: {"description": "Demasiados intentos"}})
async def cambiar_estado_como_tecnico(token: str, request: Request, response: Response, db: Session = Depends(get_db)):
    # Todo se comprueba ANTES de leer el formulario: quien no tiene un enlace vigente ni siquiera consigue que el servidor procese una foto.
    _limitar(limitador.CAMBIOS_TECNICO_IP, _ip(request))
    e = _enlace_o_404(db, token)
    _limitar(limitador.CAMBIOS_TECNICO_ENLACE, e.id)
    reporte = db.get(ReporteDanio, e.reporte_id)
    if reporte is None or _estado_enlace(e, reporte) != EstadoEnlaceTecnico.VIGENTE.value:
        raise HTTPException(status_code=400, detail="Este enlace ya no está activo: venció, el administrador lo anuló o el trabajo ya quedó cerrado.")
    try:
        largo = int(request.headers.get("content-length") or 0)
    except ValueError:
        largo = 0
    if largo > (config.MAX_UPLOAD_MB + MARGEN_MULTIPART_MB) * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"La foto es demasiado grande (máximo {config.MAX_UPLOAD_MB} MB).")

    form = await request.form()
    try:
        nuevo = EstadoTecnico(form.get("nuevo_estado"))
    except ValueError:
        raise HTTPException(status_code=422, detail="Solo puedes pasar el reporte a «En Reparacion» o «Solucionado».")
    permitidos = _permitidos(reporte.estado)
    if nuevo.value not in permitidos:
        raise HTTPException(status_code=400, detail=f"El reporte ya está en «{reporte.estado}»: " + ("desde aquí solo puedes marcarlo como Solucionado." if permitidos else "ya no admite cambios."))
    nota = _nota_limpia(form.get("nota"))
    archivo = form.get("archivo_foto")
    hay_foto = isinstance(archivo, ArchivoSubido) and bool(archivo.filename)
    if nuevo is EstadoTecnico.SOLUCIONADO:
        if len(nota) < MIN_NOTA_SOLUCIONADO:
            raise HTTPException(status_code=400, detail="Para marcarlo como solucionado escribe una nota breve de lo que hiciste (mínimo 5 caracteres).")
        if not hay_foto:
            raise HTTPException(status_code=400, detail="Para marcarlo como solucionado sube la foto de evidencia.")

    nombre_foto = await guardar_imagen_validada(archivo, con_miniatura=True) if hay_foto else None      # valida que sea una imagen real y le borra el GPS
    try:
        ahora = ahora_utc()
        anterior = reporte.estado
        reporte.estado = nuevo.value
        db.add(EvidenciaDanio(reporte_id=reporte.id, enlace_id=e.id, estado=nuevo.value, nota=nota or None, foto=nombre_foto, fecha=ahora))
        e.ultimo_uso = ahora
        if nuevo is EstadoTecnico.SOLUCIONADO:
            e.cerrado_en = ahora          # el trabajo terminó: el enlace se cierra solo
        auditar(db, None, "Técnico cambió estado de daño (enlace)", "Daño", reporte.id,
                f"{reporte.titulo}: {anterior} → {nuevo.value} · enlace #{e.id}" + (f" ({e.etiqueta})" if e.etiqueta else "") + (f" · «{nota[:80]}»" if nota else "") + (" · con foto" if nombre_foto else ""))
        _avisar(db, e, reporte, nuevo, nota)
        db.commit()
    except Exception:
        db.rollback()
        if nombre_foto:
            borrar_imagen(nombre_foto)          # no dejar una foto huérfana si algo falló al guardar
        raise
    response.headers.update(CABECERAS_API)
    cerrado = nuevo is EstadoTecnico.SOLUCIONADO
    return {"ok": True, "estado": nuevo.value, "cerrado": cerrado,
            "mensaje": "¡Gracias! El reporte quedó como solucionado y este enlace se cerró." if cerrado else "Listo: el reporte quedó «En reparación» y avisamos al residente."}


def _avisar(db: Session, e: EnlaceTecnico, reporte: ReporteDanio, nuevo: EstadoTecnico, nota: str) -> None:
    """Avisa al residente (y a su propietario si es inquilino) y al administrador que creó el enlace. Va en la MISMA transacción del cambio."""
    solucionado = nuevo is EstadoTecnico.SOLUCIONADO
    titulo = "Tu reporte quedó solucionado" if solucionado else "Tu reporte está en reparación"
    mensaje = f"«{reporte.titulo[:80]}»" + (f" · Nota del técnico: {nota[:140]}" if nota else "")
    residente = db.get(Usuario, reporte.usuario_id)
    if residente is not None:
        notificar(db, [residente], titulo, mensaje, "#/mantenimiento")
        if residente.rol == RolNombre.INQUILINO.value:
            reglas_arr.avisar_al_propietario(db, residente, titulo, mensaje, "#/mantenimiento")
    admin = db.get(Usuario, e.creado_por)
    if admin is not None and (residente is None or admin.id != residente.id):
        notificar(db, [admin], "El técnico actualizó un daño", f"«{reporte.titulo[:80]}» pasó a {nuevo.value}" + (f" · {e.etiqueta}" if e.etiqueta else ""), "#/mantenimiento")
