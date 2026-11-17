# app/routers/pagos_simulados.py — v4.2: pasarela de pagos de PRUEBAS (tipo Wompi / PSE).
# Sirve para que el cliente VEA cómo será pagar en línea cuando se conecte una pasarela real, sin mover dinero. Solo funciona con PAGOS_SIMULADOS=1.
#
# Recorrido (el mismo de una pasarela real):
#   1. POST /pagos-simulados                    → la app crea el intento y su referencia (SIM-…)
#   2. POST /pagos-simulados/{referencia}/pagar → la «pasarela» decide: Aprobado, Rechazado o Pendiente (según los datos de prueba)
#   3. GET  /pagos-simulados/{referencia}       → consulta el estado; un «Pendiente» se confirma solo unos segundos después (como el webhook de verdad)
# Reglas que también valdrán con la pasarela real: el resultado lo decide SOLO el servidor (el frontend nunca dice «pagado»), el saldo se descuenta
# una sola vez por intento (idempotente), no se guarda ningún dato de tarjeta y cada persona solo ve sus intentos.
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import arrendamientos as reglas_arr, config, limitador
from app.constantes import Delegacion, RolNombre
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import IntentoPago, Usuario, ahora_utc
from app.notificaciones import notificar
from app.routers.modulos import MSG_CARTERA, _aplicar_pago
from app.schemas.pagos_simulados import IniciarPago, IntentoOut, PagarIntento

TAG = "Pagos simulados (pasarela de pruebas)"
router = APIRouter(prefix="/pagos-simulados", tags=[TAG])
ADMIN, RESIDENTE, INQUILINO = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.INQUILINO

METODOS = ["PSE", "Tarjeta", "Nequi"]
BANCOS = [{"codigo": "aprueba", "nombre": "Banco de Pruebas · aprueba el pago"},
          {"codigo": "rechaza", "nombre": "Banco de Pruebas · rechaza el pago"},
          {"codigo": "pendiente", "nombre": "Banco de Pruebas · deja el pago en validación"}]
MINUTOS_PARA_PAGAR = 30            # un intento que nadie paga en este tiempo expira (como el enlace de pago de una pasarela real)
PENDIENTE_SEGUNDOS = 6             # cuánto tarda en «llegar» la confirmación de un pago que quedó pendiente
TARJETA_APRUEBA, TARJETA_RECHAZA, TARJETA_PENDIENTE = "4242", "4111", "0002"


def _exigir_modo_pruebas() -> None:
    if not config.PAGOS_SIMULADOS:
        raise HTTPException(status_code=403, detail="El pago en línea aún no está habilitado. Paga por transferencia y la administración registrará tu pago.")


def _salida(db: Session, i: IntentoPago) -> IntentoOut:
    titular = db.get(Usuario, i.titular_id)
    falta = None
    if i.estado == "Pendiente" and i.resuelve_en:
        falta = max(0, int((i.resuelve_en - ahora_utc()).total_seconds()) + 1)
    return IntentoOut(referencia=i.referencia, valor=i.valor, estado=i.estado, metodo=i.metodo, mensaje=i.mensaje, pago_id=i.pago_id,
                      saldo_pendiente=titular.saldo_pendiente, esta_al_dia=bool(titular.esta_al_dia), segundos_para_confirmar=falta,
                      fecha_creacion=i.fecha_creacion, metodos=METODOS, bancos=BANCOS)


def _mio(db: Session, referencia: str, usuario: Usuario) -> IntentoPago:
    """El intento solo existe para quien lo creó: para cualquier otra persona (incluido el administrador) responde 404, sin dar pistas."""
    i = db.query(IntentoPago).filter(IntentoPago.referencia == referencia, IntentoPago.usuario_id == usuario.id).with_for_update().first()
    if i is None:
        raise HTTPException(status_code=404, detail="Pago no encontrado.")
    return i


def _veredicto(datos: PagarIntento) -> tuple[str, str]:
    """La «pasarela» decide el resultado SOLO con los datos de prueba que llegaron. (En la pasarela real lo decide el banco o la red de tarjetas.)"""
    if datos.metodo == "PSE":
        if datos.banco is None:
            raise HTTPException(status_code=422, detail="Elige el banco con el que vas a pagar.")
        return {"aprueba": ("Aprobado", "Transacción aprobada por tu banco."),
                "rechaza": ("Rechazado", "Tu banco rechazó la transacción."),
                "pendiente": ("Pendiente", "Tu banco aún está validando la transacción.")}[datos.banco]
    if datos.metodo == "Tarjeta":
        if datos.terminacion is None:
            raise HTTPException(status_code=422, detail="Escribe el número de la tarjeta.")
        if datos.terminacion == TARJETA_APRUEBA:
            return "Aprobado", "Transacción aprobada."
        if datos.terminacion == TARJETA_RECHAZA:
            return "Rechazado", "Fondos insuficientes."
        if datos.terminacion == TARJETA_PENDIENTE:
            return "Pendiente", "Tu entidad aún está validando la transacción."
        return "Rechazado", f"Tarjeta no aceptada. En pruebas usa una que termine en {TARJETA_APRUEBA} (aprueba) o en {TARJETA_RECHAZA} (rechaza)."
    if datos.celular is None:
        raise HTTPException(status_code=422, detail="Escribe el celular de tu cuenta Nequi.")
    if datos.celular.endswith("1"):
        return "Rechazado", "Rechazaste la notificación en Nequi."
    if datos.celular.endswith("2"):
        return "Pendiente", "Aún no aceptas la notificación en Nequi."
    return "Aprobado", "Transacción aprobada en Nequi."


def _aprobar(db: Session, i: IntentoPago, usuario: Usuario) -> None:
    """Aplica el pago UNA sola vez (si el intento ya no está abierto, no hace nada)."""
    if i.estado not in ("Creado", "Pendiente"):
        return
    titular = db.get(Usuario, i.titular_id)
    por_delegacion = titular.id != usuario.id
    try:
        pago = _aplicar_pago(db, titular, i.valor, usuario, "Pagó administración (pasarela de pruebas)" + (" por delegación del propietario" if por_delegacion else ""),
                             f" · ref. {i.referencia}" + (f" · pagó {usuario.nombre_completo}" if por_delegacion else ""))["pago"]
    except HTTPException as e:               # p. ej. el administrador registró otro pago mientras tanto y el saldo ya no alcanza
        i.estado, i.mensaje, i.fecha_resolucion = "Rechazado", f"No se pudo aplicar el pago: {e.detail}", ahora_utc()
        return
    i.estado, i.pago_id, i.fecha_resolucion, i.resuelve_en = "Aprobado", pago.id, ahora_utc(), None
    if por_delegacion:
        notificar(db, [titular], f"{usuario.nombre_completo} pagó la administración",
                  f"${i.valor:,}".replace(",", ".") + " en nombre de tu apartamento. Su comprobante está en Mis pagos.", "#/cartera")


def _actualizar(db: Session, i: IntentoPago, usuario: Usuario) -> None:
    """Pone al día el estado del intento: expira el que nadie pagó y confirma el que estaba «Pendiente» cuando ya le tocaba (el «webhook»)."""
    ahora = ahora_utc()
    if i.estado == "Creado" and ahora - i.fecha_creacion > timedelta(minutes=MINUTOS_PARA_PAGAR):
        i.estado, i.mensaje, i.fecha_resolucion = "Expirado", "El tiempo para pagar se agotó. Inicia el pago de nuevo.", ahora
    elif i.estado == "Pendiente" and i.resuelve_en and ahora >= i.resuelve_en:
        _aprobar(db, i, usuario)
        if i.estado == "Aprobado":
            i.mensaje = "Transacción aprobada."


@router.post("", response_model=IntentoOut, status_code=201, summary="Iniciar un pago en la pasarela de pruebas",
             description="Roles: **Residente**, **Administrador** e **Inquilino** (solo si su propietario le delegó los pagos). Crea el intento y devuelve su referencia `SIM-…`. "
                         "El valor no puede superar el saldo pendiente. **Solo con `PAGOS_SIMULADOS=1`**; si no, 403.",
             responses={400: {"description": "Valor inválido o sin saldo"}, 403: {"description": "Pagos simulados desactivados o sin delegación"}, 429: {"description": "Demasiados intentos"}})
def iniciar(datos: IniciarPago, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    _exigir_modo_pruebas()
    if not limitador.PAGOS_SIMULADOS_USUARIO.intentar(usuario.id):
        raise HTTPException(status_code=429, detail="Hiciste muchos intentos de pago seguidos. Espera unos minutos.")
    titular = reglas_arr.titular_con_delegacion(db, usuario, Delegacion.PAGAR, MSG_CARTERA)
    if titular.saldo_pendiente <= 0:
        raise HTTPException(status_code=400, detail="No hay saldo pendiente por pagar.")
    if datos.valor > titular.saldo_pendiente:
        raise HTTPException(status_code=400, detail=f"El valor excede el saldo pendiente (${titular.saldo_pendiente}).")
    i = IntentoPago(referencia="SIM-" + secrets.token_hex(5).upper(), usuario_id=usuario.id, titular_id=titular.id, valor=datos.valor)
    db.add(i)
    db.commit()
    db.refresh(i)
    return _salida(db, i)


@router.post("/{referencia}/pagar", response_model=IntentoOut, summary="Pagar un intento (la pasarela decide el resultado)",
             description="Roles: los mismos de `iniciar`, y solo sobre **sus** intentos. Recibe el método y los datos de **prueba**: PSE → `banco` (`aprueba`, `rechaza`, `pendiente`); "
                         "Tarjeta → `terminacion` (4242 aprueba, 4111 rechaza, 0002 queda pendiente); Nequi → `celular` (termina en 1 rechaza, en 2 queda pendiente). "
                         "Es **idempotente**: si el intento ya terminó, devuelve su resultado y no cobra de nuevo.",
             responses={403: {"description": "Pagos simulados desactivados"}, 404: {"description": "Intento no encontrado"}, 422: {"description": "Faltan datos del método"}, 429: {"description": "Demasiados intentos"}})
def pagar(referencia: str, datos: PagarIntento, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    _exigir_modo_pruebas()
    if not limitador.PAGOS_SIMULADOS_USUARIO.intentar(usuario.id):
        raise HTTPException(status_code=429, detail="Hiciste muchos intentos de pago seguidos. Espera unos minutos.")
    i = _mio(db, referencia, usuario)
    _actualizar(db, i, usuario)
    if i.estado == "Creado":                                   # solo un intento sin pagar puede decidirse (un «Pendiente» espera su confirmación)
        estado, mensaje = _veredicto(datos)
        i.metodo, i.mensaje = datos.metodo, mensaje
        if estado == "Aprobado":
            _aprobar(db, i, usuario)
            if i.estado == "Aprobado":
                i.mensaje = mensaje
        elif estado == "Pendiente":
            i.estado, i.resuelve_en = "Pendiente", ahora_utc() + timedelta(seconds=PENDIENTE_SEGUNDOS)
        else:
            i.estado, i.fecha_resolucion = "Rechazado", ahora_utc()
    db.commit()
    db.refresh(i)
    return _salida(db, i)


@router.get("/{referencia}", response_model=IntentoOut, summary="Consultar el estado de un pago de prueba",
            description="Roles: los mismos de `iniciar`, solo sobre **sus** intentos. Un pago «Pendiente» se confirma solo unos segundos después (como el aviso que enviaría una pasarela real).",
            responses={403: {"description": "Pagos simulados desactivados"}, 404: {"description": "Intento no encontrado"}})
def consultar(referencia: str, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    _exigir_modo_pruebas()
    i = _mio(db, referencia, usuario)
    _actualizar(db, i, usuario)
    db.commit()
    db.refresh(i)
    return _salida(db, i)
