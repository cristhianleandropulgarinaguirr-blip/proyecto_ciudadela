# app/routers/asamblea_acta.py
# Acta de la asamblea — V5.4, Fase 4 (Art. 47 de la Ley 675 de 2001). Las reglas viven en app/asamblea_acta.py; aquí solo se traduce HTTP.
#
# Ciclo:  (asamblea en sesión o cerrada) editar borrador → descargar borrador con marca de agua →
#         (asamblea CERRADA) sellar = congelar con huella SHA-256 → subir copia firmada → publicar a los propietarios → verificar integridad cuando se quiera.
# Solo el Administrador prepara y sella el acta. Sellar y publicar (irreversibles) piden la contraseña de nuevo (`reauth_admin`, v5.3). El residente solo ve el acta ya PUBLICADA. Guardia e inquilino no tienen acceso.
import hashlib
import json

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app import asamblea_acta as acta_reglas, asambleas as reglas
from app.archivos import guardar_pdf_validado, leer_documento
from app.auditoria import auditar
from app.config import ASAMBLEA_ACTA_DIAS_HABILES, MAX_PDF_MB
from app.constantes import EstadoActa, EstadoAsamblea, RolNombre
from app.database import get_db
from app.dependencies import reauth_admin, requiere_roles
from app.models import Asamblea, AsambleaActa, ahora_utc
from app.notificaciones import notificar
from app.routers.asambleas import _con_acceso, _residentes_activos_lista
from app.schemas import asamblea_acta as esq

TAG = "Acta de la Asamblea"
router = APIRouter(prefix="/asambleas", tags=[TAG])
ADMIN, RESIDENTE = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE
ESTADOS_CON_ACTA = (EstadoAsamblea.EN_SESION.value, EstadoAsamblea.CERRADA.value)
SIN_CACHE = {"Cache-Control": "private, no-store"}


# ---------------------------------------------------------------- ayudas
def _admin_asamblea(db: Session, asamblea_id: int, bloquear: bool = False) -> Asamblea:
    """La asamblea para el administrador; el acta solo existe mientras se reúne o después de cerrarse."""
    a = reglas.obtener(db, asamblea_id, bloquear=bloquear)
    if a.estado not in ESTADOS_CON_ACTA:
        raise HTTPException(status_code=409, detail="El acta se prepara cuando la asamblea está en sesión o ya cerrada.")
    return a


def _motivo_no_sellar(a: Asamblea, acta: AsambleaActa | None) -> str | None:
    if a.estado != EstadoAsamblea.CERRADA.value:
        return "Cierra primero la asamblea: el acta se sella cuando la reunión ya terminó."
    if acta is None or not acta.presidente_nombre:
        return "Falta el nombre del presidente de la reunión."
    if not acta.secretario_nombre:
        return "Falta el nombre del secretario de la reunión."
    return None


def _vista_admin(a: Asamblea, acta: AsambleaActa | None) -> esq.ActaResponse:
    sellada = acta_reglas.esta_sellada(acta)
    publicada = bool(acta and acta.publicada_en)
    vencido = (not publicada) and acta_reglas.plazo_vencido(a)
    limite = acta_reglas.limite_publicacion(a)
    motivo = None if sellada else _motivo_no_sellar(a, acta)
    avisos: list[str] = []
    if vencido:
        avisos.append(f"El plazo de {ASAMBLEA_ACTA_DIAS_HABILES} días hábiles para poner el acta a disposición de los propietarios venció el {limite.strftime('%d/%m/%Y')} (Art. 47, Ley 675). Publícala cuanto antes.")
    if a.estado == EstadoAsamblea.CERRADA.value and not sellada and (acta is None or not acta.desarrollo):
        avisos.append("El desarrollo del orden del día está vacío: el secretario debe redactarlo antes de sellar.")
    if sellada and not (acta and acta.firmada_archivo):
        avisos.append("Aún no has subido la copia firmada por el presidente y el secretario. El acta solo tiene plena validez firmada.")
    return esq.ActaResponse(
        asamblea_id=a.id, estado=acta.estado if acta else "Sin iniciar", editable=(not sellada) and a.estado in ESTADOS_CON_ACTA, publicada=publicada,
        presidente_nombre=acta.presidente_nombre if acta else None, secretario_nombre=acta.secretario_nombre if acta else None,
        comision=acta.comision if acta else None, desarrollo=acta.desarrollo if acta else None,
        sellada_en=acta.sellada_en if acta else None, contenido_hash=acta.contenido_hash if acta else None,
        tiene_firmada=bool(acta and acta.firmada_archivo), firmada_en=acta.firmada_en if acta else None, firmada_hash=acta.firmada_hash if acta else None,
        publicada_en=acta.publicada_en if acta else None, limite_publicacion=limite, plazo_vencido=vencido,
        puede_sellar=(not sellada) and motivo is None, motivo_no_sellar=motivo, advertencias=avisos)


def _vista_residente(a: Asamblea, acta: AsambleaActa) -> esq.ActaResponse:
    """Lo que ve un propietario: que el acta ya está publicada, cuándo y su huella. El texto lo lee en el PDF."""
    return esq.ActaResponse(asamblea_id=a.id, estado=acta.estado, publicada=True, sellada_en=acta.sellada_en, contenido_hash=acta.contenido_hash,
                            tiene_firmada=bool(acta.firmada_archivo), firmada_en=acta.firmada_en, publicada_en=acta.publicada_en)


def _pdf(datos: bytes, nombre: str) -> Response:
    return Response(content=datos, media_type="application/pdf", headers={**SIN_CACHE, "Content-Disposition": f'inline; filename="{nombre}"'})


def _sellada_o_409(acta: AsambleaActa | None) -> AsambleaActa:
    if not acta_reglas.esta_sellada(acta):
        raise HTTPException(status_code=409, detail="El acta todavía no está sellada.")
    return acta


# ---------------------------------------------------------------- ver y editar el borrador
@router.get("/{asamblea_id}/acta", response_model=esq.ActaResponse, summary="Ver el estado del acta",
            description="**Administrador**: el borrador completo, el plazo de publicación y qué falta. **Residente**: solo si el acta ya fue publicada (si no, 404).",
            responses={404: {"description": "El acta aún no está publicada"}, 409: {"description": "La asamblea aún no está en sesión ni cerrada"}})
def ver_acta(asamblea_id: int, db: Session = Depends(get_db), usuario=Depends(requiere_roles(ADMIN, RESIDENTE))):
    if usuario.rol == ADMIN.value:
        a = _admin_asamblea(db, asamblea_id)
        return _vista_admin(a, acta_reglas.acta_de(db, a.id))
    a = _con_acceso(db, asamblea_id, usuario)
    acta = acta_reglas.acta_de(db, a.id)
    if acta is None or acta.publicada_en is None:
        raise HTTPException(status_code=404, detail="El acta todavía no ha sido publicada.")
    return _vista_residente(a, acta)


@router.put("/{asamblea_id}/acta", response_model=esq.ActaResponse, summary="Guardar el borrador del acta",
            description="Solo **Administrador**. Presidente, secretario, comisión verificadora y desarrollo de la reunión. Solo se cambia lo que se envía. Una vez sellada, el acta no se edita.",
            responses={409: {"description": "La asamblea no está en sesión/cerrada o el acta ya está sellada"}})
def guardar_borrador(asamblea_id: int, cuerpo: esq.ActaEdit, db: Session = Depends(get_db), admin=Depends(requiere_roles(ADMIN))):
    a = _admin_asamblea(db, asamblea_id, bloquear=True)
    acta = acta_reglas.acta_de(db, a.id)
    if acta_reglas.esta_sellada(acta):
        raise HTTPException(status_code=409, detail="El acta ya está sellada: no se puede modificar.")
    if acta is None:
        acta = AsambleaActa(asamblea_id=a.id, estado=EstadoActa.BORRADOR.value)
        db.add(acta)
    cambios = cuerpo.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(acta, campo, valor)
    acta.editada_por = admin.id
    auditar(db, admin, "Editó el borrador del acta", "Asamblea", a.id, "campos: " + (", ".join(sorted(cambios)) or "ninguno"))
    db.commit()
    db.refresh(acta)
    return _vista_admin(a, acta)


@router.get("/{asamblea_id}/acta/borrador.pdf", summary="Descargar el borrador del acta (con marca de agua)",
            description="Solo **Administrador**. Se genera con lo registrado hasta este momento y lleva la marca «BORRADOR»: no tiene valor hasta sellarla y firmarla.",
            responses={409: {"description": "El acta ya está sellada (descarga la definitiva)"}})
def borrador_pdf(asamblea_id: int, db: Session = Depends(get_db), admin=Depends(requiere_roles(ADMIN))):
    a = _admin_asamblea(db, asamblea_id)
    acta = acta_reglas.acta_de(db, a.id)
    if acta_reglas.esta_sellada(acta):
        raise HTTPException(status_code=409, detail="El acta ya está sellada: descarga el acta definitiva.")
    datos = acta_reglas.render_pdf(acta_reglas.construir_contenido(db, a, acta), borrador=True)
    return _pdf(datos, f"acta-borrador-asamblea-{a.id}.pdf")


# ---------------------------------------------------------------- sellar (congelar)
@router.post("/{asamblea_id}/acta/sellar", response_model=esq.ActaResponse, summary="Sellar (congelar) el acta",
             description="Solo **Administrador**, con la asamblea **cerrada**. Guarda una copia congelada de todo el contenido con su huella SHA-256, que además queda en la bitácora encadenada. "
                         "**No se puede deshacer**: después el texto, los asistentes y los resultados ya no cambian. Pide la contraseña de nuevo (acción sensible).",
             responses={400: {"description": "Faltan el presidente o el secretario"}, 409: {"description": "La asamblea no está cerrada, el acta ya estaba sellada o la bitácora fue alterada"}})
def sellar(asamblea_id: int, db: Session = Depends(get_db), admin=Depends(reauth_admin)):
    a = _admin_asamblea(db, asamblea_id, bloquear=True)
    acta = acta_reglas.acta_de(db, a.id)
    if acta_reglas.esta_sellada(acta):
        raise HTTPException(status_code=409, detail="El acta ya está sellada.")
    motivo = _motivo_no_sellar(a, acta)
    if motivo:
        raise HTTPException(status_code=409 if a.estado != EstadoAsamblea.CERRADA.value else 400, detail=motivo)
    integra, danada, _ = reglas.verificar_bitacora(db, a.id)
    if not integra:
        raise HTTPException(status_code=409, detail=f"No se puede sellar: la bitácora de la asamblea fue alterada (se rompe en el evento n.º {danada}). Revisa la base de datos antes de continuar.")
    contenido = acta_reglas.construir_contenido(db, a, acta)
    h = acta_reglas.huella(contenido)
    acta.contenido = acta_reglas._canonico(contenido)
    acta.contenido_hash = h
    acta.estado = EstadoActa.SELLADA.value
    acta.sellada_en, acta.sellada_por = ahora_utc(), admin.id
    votaciones = sum(1 for v in contenido["evidencia"]["votaciones"] if v["estado"] == "Cerrada")
    reglas.registrar_evento(db, a.id, "ActaSellada", admin, detalle=f"Acta sellada · {len(contenido['evidencia']['asistentes'])} asistentes · {votaciones} votación(es) · huella {h}")
    auditar(db, admin, "Selló el acta de una asamblea", "Asamblea", a.id, f"huella {h[:16]}")
    db.commit()
    db.refresh(acta)
    return _vista_admin(a, acta)


@router.get("/{asamblea_id}/acta.pdf", summary="Descargar el acta definitiva",
            description="El acta sellada, dibujada desde su copia congelada (siempre sale igual). **Administrador**: desde que se sella. **Residente**: solo cuando ya fue publicada. Si hay copia firmada, descárgala en `/acta/firmada`.",
            responses={404: {"description": "No publicada (para el residente)"}, 409: {"description": "Aún no está sellada"}})
def acta_pdf(asamblea_id: int, db: Session = Depends(get_db), usuario=Depends(requiere_roles(ADMIN, RESIDENTE))):
    if usuario.rol == ADMIN.value:
        a = _admin_asamblea(db, asamblea_id)
        acta = _sellada_o_409(acta_reglas.acta_de(db, a.id))
    else:
        a = _con_acceso(db, asamblea_id, usuario)
        acta = acta_reglas.acta_de(db, a.id)
        if acta is None or acta.publicada_en is None:
            raise HTTPException(status_code=404, detail="El acta todavía no ha sido publicada.")
    datos = acta_reglas.render_pdf(json.loads(acta.contenido), borrador=False, huella_acta=acta.contenido_hash, sellada_en=acta.sellada_en)
    return _pdf(datos, f"acta-asamblea-{a.id}.pdf")


# ---------------------------------------------------------------- copia firmada
@router.post("/{asamblea_id}/acta/firmada", response_model=esq.ActaResponse, summary="Subir la copia firmada del acta",
             description="Solo **Administrador**. El PDF escaneado con las firmas del presidente y el secretario. Se guarda su huella SHA-256 y queda en la bitácora. "
                         "Se puede reemplazar mientras el acta no se haya publicado.",
             responses={400: {"description": "No es un PDF válido"}, 409: {"description": "El acta no está sellada o ya fue publicada"}})
async def subir_firmada(asamblea_id: int, archivo: UploadFile = File(..., description="PDF escaneado y firmado"), db: Session = Depends(get_db), admin=Depends(requiere_roles(ADMIN))):
    a = _admin_asamblea(db, asamblea_id, bloquear=True)
    acta = _sellada_o_409(acta_reglas.acta_de(db, a.id))
    if acta.publicada_en is not None:
        raise HTTPException(status_code=409, detail="El acta ya fue publicada: la copia firmada ya no se puede reemplazar.")
    contenido = await archivo.read(MAX_PDF_MB * 1024 * 1024 + 1)         # se lee una vez para la huella y se rebobina para que `guardar_pdf_validado` valide tipo, tamaño y firma «%PDF-»
    await archivo.seek(0)
    guardado, _ = await guardar_pdf_validado(archivo)
    huella = hashlib.sha256(contenido).hexdigest()
    reemplaza = acta.firmada_archivo is not None
    acta.firmada_archivo, acta.firmada_hash, acta.firmada_en, acta.firmada_por = guardado, huella, ahora_utc(), admin.id
    reglas.registrar_evento(db, a.id, "ActaFirmada", admin, detalle=f"{'Se reemplazó la' if reemplaza else 'Se subió la'} copia firmada del acta · SHA-256 {huella}")
    auditar(db, admin, "Subió la copia firmada del acta", "Asamblea", a.id, f"sha256 {huella[:16]}")
    db.commit()
    db.refresh(acta)
    return _vista_admin(a, acta)


@router.get("/{asamblea_id}/acta/firmada", summary="Descargar la copia firmada",
            description="**Administrador**: desde que se sube. **Residente**: solo cuando el acta ya fue publicada.", responses={404: {"description": "No hay copia firmada disponible"}})
def descargar_firmada(asamblea_id: int, db: Session = Depends(get_db), usuario=Depends(requiere_roles(ADMIN, RESIDENTE))):
    if usuario.rol == ADMIN.value:
        a = _admin_asamblea(db, asamblea_id)
    else:
        a = _con_acceso(db, asamblea_id, usuario)
    acta = acta_reglas.acta_de(db, a.id)
    if acta is None or not acta.firmada_archivo or (usuario.rol != ADMIN.value and acta.publicada_en is None):
        raise HTTPException(status_code=404, detail="No hay copia firmada disponible.")
    datos = leer_documento(acta.firmada_archivo)
    if datos is None:
        raise HTTPException(status_code=404, detail="El archivo de la copia firmada no está disponible.")
    return _pdf(datos, f"acta-firmada-asamblea-{a.id}.pdf")


# ---------------------------------------------------------------- publicar y verificar
@router.post("/{asamblea_id}/acta/publicar", response_model=esq.ActaResponse, summary="Publicar el acta a los propietarios",
             description="Solo **Administrador**. Deja el acta a disposición de los propietarios (Art. 47) y les avisa. Exige el acta sellada; la copia firmada es muy recomendable pero no obligatoria (el plazo legal es corto). Pide la contraseña de nuevo (acción sensible).",
             responses={409: {"description": "El acta no está sellada o ya estaba publicada"}})
def publicar(asamblea_id: int, db: Session = Depends(get_db), admin=Depends(reauth_admin)):
    a = _admin_asamblea(db, asamblea_id, bloquear=True)
    acta = _sellada_o_409(acta_reglas.acta_de(db, a.id))
    if acta.publicada_en is not None:
        raise HTTPException(status_code=409, detail="El acta ya fue publicada.")
    fuera_de_plazo = acta_reglas.plazo_vencido(a)
    acta.publicada_en, acta.publicada_por = ahora_utc(), admin.id
    reglas.registrar_evento(db, a.id, "ActaPublicada", admin, detalle=f"Acta publicada a los propietarios · {'con' if acta.firmada_archivo else 'SIN'} copia firmada" + (" · fuera del plazo legal" if fuera_de_plazo else ""))
    auditar(db, admin, "Publicó el acta de una asamblea", "Asamblea", a.id, "fuera de plazo" if fuera_de_plazo else None)
    notificar(db, _residentes_activos_lista(db), f"Acta disponible: {a.titulo}", "Ya puedes consultar el acta de la asamblea.", "#/asambleas")
    db.commit()
    db.refresh(acta)
    return _vista_admin(a, acta)


@router.get("/{asamblea_id}/acta/verificar", response_model=esq.VerificacionResponse, summary="Verificar la integridad del acta",
            description="Solo **Administrador**. Recalcula todo y lo compara con lo congelado: texto del acta, asistentes y votos actuales, cadena de la bitácora y copia firmada. Si algo no coincide, alguien modificó datos después de sellar.",
            responses={409: {"description": "El acta aún no está sellada"}})
def verificar(asamblea_id: int, db: Session = Depends(get_db), admin=Depends(requiere_roles(ADMIN))):
    a = _admin_asamblea(db, asamblea_id)
    acta = _sellada_o_409(acta_reglas.acta_de(db, a.id))
    return acta_reglas.verificar(db, a, acta)
