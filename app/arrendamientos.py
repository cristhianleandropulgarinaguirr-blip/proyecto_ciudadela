# app/arrendamientos.py
# Reglas del rol Inquilino (sin rutas: las usan los routers y la verificación de sesión).
#   · titular_de    → de quién es el estado financiero (mora) que hereda un inquilino: el del propietario.
#   · contrato_vigente → ¿el contrato sigue vigente? Si ya venció, lo cierra en ese momento (no hace falta un proceso aparte).
#   · finalizar     → cierra el acceso: desactiva la cuenta, revoca sesiones y pases QR y retira a sus visitantes autorizados.
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app import sesiones
from app.auditoria import auditar
from fastapi import HTTPException

from app.constantes import Delegacion, EstadoArrendamiento, EstadoQR, RolNombre, TipoQR
from app.models import Arrendamiento, CodigoQR, Usuario, VisitanteAutorizado, ahora_utc
from app.notificaciones import notificar, usuarios_activos

HORA_COLOMBIA = timezone(timedelta(hours=-5))     # Colombia no tiene horario de verano


def ahora_local() -> datetime:
    """Hora del conjunto, sin zona (así se guarda `fecha_fin`: el contrato termina al acabar ese día, hora local)."""
    return datetime.now(HORA_COLOMBIA).replace(tzinfo=None)


def contrato_activo(db: Session, inquilino_id: int) -> Optional[Arrendamiento]:
    return (db.query(Arrendamiento)
            .filter(Arrendamiento.inquilino_id == inquilino_id, Arrendamiento.estado == EstadoArrendamiento.ACTIVO.value)
            .order_by(Arrendamiento.id.desc()).first())


def finalizar(db: Session, contrato: Arrendamiento, motivo: str, actor: Optional[Usuario] = None,
              estado: EstadoArrendamiento = EstadoArrendamiento.FINALIZADO) -> None:
    """Cierra el contrato y todo lo que el inquilino tenía abierto. No hace commit: lo hace quien llama."""
    contrato.estado, contrato.motivo_cierre, contrato.fecha_decision = estado.value, motivo[:200], ahora_utc()
    inquilino = db.get(Usuario, contrato.inquilino_id)
    if inquilino is not None:
        inquilino.esta_activo = False
        sesiones.revocar_todas(db, inquilino.id)
        for pase in db.query(CodigoQR).filter(CodigoQR.usuario_id == inquilino.id, CodigoQR.tipo == TipoQR.VISITANTE.value,
                                              CodigoQR.estado == EstadoQR.ACTIVO.value).all():
            pase.estado = EstadoQR.REVOCADO.value      # los que ya están dentro conservan la salida (siempre se permite)
        for v in db.query(VisitanteAutorizado).filter(VisitanteAutorizado.usuario_id == inquilino.id, VisitanteAutorizado.activo.is_(True)).all():
            v.activo = False
    auditar(db, actor, "Cerró arrendamiento" if estado == EstadoArrendamiento.FINALIZADO else "Rechazó arrendamiento", "Arrendamiento", contrato.id,
            f"{inquilino.nombre_completo if inquilino else contrato.inquilino_id} · {contrato.apartamento or 'sin apto.'} · {motivo}")
    if estado == EstadoArrendamiento.FINALIZADO:
        propietario = db.get(Usuario, contrato.propietario_id)
        quien = inquilino.nombre_completo if inquilino else "Tu inquilino"
        notificar(db, [propietario] if propietario and (actor is None or propietario.id != actor.id) else [],
                  f"Terminó el arrendamiento de {quien}", f"{motivo}. Ya no tiene acceso a la aplicación.", "#/inquilinos")


def contrato_vigente(db: Session, inquilino: Usuario) -> bool:
    """True si el inquilino tiene un contrato activo y dentro de fechas. Si ya venció, lo cierra y devuelve False
    (quien llama debe hacer commit para dejar guardado el cierre)."""
    contrato = contrato_activo(db, inquilino.id)
    if contrato is None:
        return False
    if contrato.fecha_fin < ahora_local():
        finalizar(db, contrato, "El contrato llegó a su fecha de fin")
        return False
    return True


def vencer_contratos(db: Session) -> int:
    """Cierra todos los contratos activos que ya vencieron (se llama al listar arrendamientos). No hace commit."""
    vencidos = (db.query(Arrendamiento)
                .filter(Arrendamiento.estado == EstadoArrendamiento.ACTIVO.value, Arrendamiento.fecha_fin < ahora_local()).all())
    for c in vencidos:
        finalizar(db, c, "El contrato llegó a su fecha de fin")
    return len(vencidos)


def titular_de(db: Session, usuario: Usuario) -> Usuario:
    """Quién responde por el apartamento: el propietario si `usuario` es inquilino con contrato activo; si no, el mismo usuario.
    Así la mora del propietario también bloquea las reservas de su inquilino."""
    if usuario.rol != RolNombre.INQUILINO.value:
        return usuario
    contrato = contrato_activo(db, usuario.id)
    return (db.get(Usuario, contrato.propietario_id) if contrato else None) or usuario


def delegaciones(db: Session, usuario: Usuario) -> list[str]:
    """Lo que el propietario le delegó a este usuario. Solo aplica a inquilinos con contrato activo; para los demás roles, nada."""
    if usuario.rol != RolNombre.INQUILINO.value:
        return []
    c = contrato_activo(db, usuario.id)
    if c is None:
        return []
    return [d.value for d, activa in ((Delegacion.PAGAR, c.puede_pagar), (Delegacion.VOTAR, c.puede_votar)) if activa]


def titular_con_delegacion(db: Session, usuario: Usuario, permiso: Delegacion, mensaje: str) -> Usuario:
    """Para las acciones que son del propietario (pagar, votar). Si `usuario` no es inquilino, devuelve al mismo usuario.
    Si es inquilino: solo pasa con la delegación activa (y entonces actúa como el propietario); si no, responde 403."""
    if usuario.rol != RolNombre.INQUILINO.value:
        return usuario
    if permiso.value not in delegaciones(db, usuario):
        raise HTTPException(status_code=403, detail=mensaje)
    return titular_de(db, usuario)


def inquilinos_con_delegacion(db: Session, permiso: Delegacion) -> list[Usuario]:
    """Inquilinos activos a quienes su propietario les delegó este permiso (para avisarles, p. ej., de una votación nueva)."""
    columna = Arrendamiento.puede_votar if permiso == Delegacion.VOTAR else Arrendamiento.puede_pagar
    return (db.query(Usuario).join(Arrendamiento, Arrendamiento.inquilino_id == Usuario.id)
            .filter(Arrendamiento.estado == EstadoArrendamiento.ACTIVO.value, columna.is_(True), Usuario.esta_activo.is_(True)).all())


def avisar_al_propietario(db: Session, inquilino: Usuario, titulo: str, mensaje: Optional[str] = None, enlace: Optional[str] = None) -> None:
    """Cuando el inquilino hace algo que afecta al apartamento (reserva, daño), el propietario se entera."""
    contrato = contrato_activo(db, inquilino.id)
    if contrato is not None:
        notificar(db, [db.get(Usuario, contrato.propietario_id)], titulo, mensaje, enlace)


def administradores(db: Session) -> list[Usuario]:
    return usuarios_activos(db, [RolNombre.ADMINISTRADOR])
