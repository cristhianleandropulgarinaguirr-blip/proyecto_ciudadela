# app/routers/modulos.py
# Módulos de negocio: reservas, daños, administración (cartera) y portería.
# Cada ruta declara qué roles pueden usarla con Depends(requiere_roles(...)).
import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session, aliased

from app import config
from app.archivos import guardar_imagen_validada, leer_imagen
from app.auditoria import auditar
from app.notificaciones import notificar
from app.constantes import EstadoDanio, EstadoReserva, RolNombre
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import Pago, ReporteDanio, Reserva, Usuario, VehiculoVisitante, ahora_utc
from app.schemas.negocio import (
    OcupacionDia, PagoRegistroResponse,
    EstadoCuentaResponse, MensajeResponse, PagoResponse, ReservaCreate,
    HistorialVehiculosResponse, ReservaResponse, ReporteResponse, VehiculoHistorialItem, VehiculoResponse,
)

logger = logging.getLogger("conjunto")
router = APIRouter()

ADMIN = RolNombre.ADMINISTRADOR
RESIDENTE = RolNombre.RESIDENTE
GUARDIA = RolNombre.GUARDIA

# =========================================================================
#                          MÓDULO DE RESERVAS
# =========================================================================
TAG_RESERVAS = "Reservas de Áreas Comunes"


def _hay_reserva_aprobada(db: Session, zona: str, fecha: datetime, excluir_id: int | None = None) -> bool:
    """¿Ya existe una reserva APROBADA de esa zona ese mismo día?"""
    inicio = datetime(fecha.year, fecha.month, fecha.day)
    consulta = db.query(Reserva).filter(
        Reserva.zona_comun == zona,
        Reserva.estado == EstadoReserva.APROBADA.value,
        Reserva.fecha_reserva >= inicio,
        Reserva.fecha_reserva < inicio + timedelta(days=1),
    )
    if excluir_id is not None:
        consulta = consulta.filter(Reserva.id != excluir_id)
    return consulta.first() is not None


def _vista_reservas(db: Session, reservas: list[Reserva]) -> list[ReservaResponse]:
    """Agrega nombre y apartamento de quien reservó: el guardia los necesita para validar a quien llega a la zona."""
    ids = {r.usuario_id for r in reservas}
    duenos = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_(ids)).all()} if ids else {}
    salida = []
    for r in reservas:
        d = duenos.get(r.usuario_id)
        salida.append(ReservaResponse(id=r.id, usuario_id=r.usuario_id, zona_comun=r.zona_comun, fecha_reserva=r.fecha_reserva,
                                      estado=r.estado, fecha_creacion=r.fecha_creacion,
                                      usuario_nombre=d.nombre_completo if d else None, apartamento=d.apartamento if d else None))
    return salida


@router.post("/reservas/registrar", response_model=ReservaResponse, status_code=status.HTTP_201_CREATED,
             tags=[TAG_RESERVAS], summary="Solicitar una reserva",
             description="Roles: **Residente**, **Administrador**. La reserva se crea a nombre del usuario del token. "
             "Se rechaza si el apartamento está en mora o si la zona ya está aprobada para ese día.",
             responses={400: {"description": "Zona ya reservada ese día"}, 403: {"description": "Usuario en mora o sin permiso"}})
def crear_reserva(reserva_in: ReservaCreate, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(requiere_roles(RESIDENTE, ADMIN))):
    if not usuario.esta_al_dia:
        raise HTTPException(status_code=403, detail="Reserva denegada: el apartamento registra saldos en mora con la administración.")

    if _hay_reserva_aprobada(db, reserva_in.zona_comun, reserva_in.fecha_reserva):
        raise HTTPException(status_code=400, detail=f"Lo sentimos, '{reserva_in.zona_comun}' ya se encuentra reservado para este día.")

    nueva = Reserva(usuario_id=usuario.id, zona_comun=reserva_in.zona_comun,
                    fecha_reserva=reserva_in.fecha_reserva, estado=EstadoReserva.PENDIENTE.value)
    db.add(nueva)
    db.flush()
    auditar(db, usuario, "Solicitó reserva", "Reserva", nueva.id, f"{nueva.zona_comun} · {nueva.fecha_reserva:%Y-%m-%d %H:%M}")
    db.commit()
    db.refresh(nueva)
    return _vista_reservas(db, [nueva])[0]


@router.get("/reservas/mis-reservas", response_model=list[ReservaResponse], tags=[TAG_RESERVAS],
            summary="Ver mis reservas", description="Cualquier usuario autenticado ve solo las suyas.")
def mis_reservas(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    return _vista_reservas(db, db.query(Reserva).filter(Reserva.usuario_id == usuario.id).order_by(Reserva.fecha_reserva).all())


@router.get("/reservas/ocupacion", response_model=list[OcupacionDia], tags=[TAG_RESERVAS], summary="Ver qué días están ocupados (calendario)",
            description="Roles: **todos**. Para pintar el calendario: devuelve solo el día y el estado (`Aprobada` = ocupado, `Pendiente` = alguien lo pidió), "
                        "**sin nombres** de quién reservó. `mes` con formato `AAAA-MM`.",
            responses={422: {"description": "Mes inválido"}})
def ocupacion(zona: str = Query(..., min_length=3, max_length=50), mes: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
              db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    anio, m = int(mes[:4]), int(mes[5:])
    inicio = datetime(anio, m, 1)
    fin = datetime(anio + (m == 12), 1 if m == 12 else m + 1, 1)
    filas = db.query(Reserva).filter(Reserva.zona_comun == zona, Reserva.fecha_reserva >= inicio, Reserva.fecha_reserva < fin,
                                     Reserva.estado.in_([EstadoReserva.APROBADA.value, EstadoReserva.PENDIENTE.value])).all()
    dias: dict = {}
    for r in filas:   # si el mismo día hay una aprobada y una pendiente, manda la aprobada
        dia = r.fecha_reserva.date()
        if dias.get(dia) != EstadoReserva.APROBADA.value:
            dias[dia] = r.estado
    return [OcupacionDia(dia=d, estado=e) for d, e in sorted(dias.items())]


@router.get("/reservas/listar", response_model=list[ReservaResponse], tags=[TAG_RESERVAS],
            summary="Listar todas las reservas", description="Roles: **Administrador**, **Guardia**. Incluye nombre y apartamento de quien reservó, para que portería valide quién llega a la zona.")
def listar_todas_las_reservas(db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(ADMIN, GUARDIA))):
    return _vista_reservas(db, db.query(Reserva).order_by(Reserva.fecha_reserva).all())


@router.patch("/reservas/cambiar-estado/{reserva_id}", response_model=ReservaResponse, tags=[TAG_RESERVAS],
              summary="Aprobar / cancelar una reserva (administrador)", description="Solo **Administrador**.",
              responses={404: {"description": "La reserva no existe"}, 400: {"description": "Conflicto con otra reserva aprobada"}})
def cambiar_estado_reserva(reserva_id: int, nuevo_estado: EstadoReserva, db: Session = Depends(get_db),
                           admin: Usuario = Depends(requiere_roles(ADMIN))):
    reserva = db.get(Reserva, reserva_id)
    if reserva is None:
        raise HTTPException(status_code=404, detail="La reserva no existe.")
    if nuevo_estado == EstadoReserva.APROBADA and _hay_reserva_aprobada(db, reserva.zona_comun, reserva.fecha_reserva, reserva.id):
        raise HTTPException(status_code=400, detail="Ya existe otra reserva aprobada para esa zona ese día.")
    anterior, reserva.estado = reserva.estado, nuevo_estado.value
    auditar(db, admin, f"Reserva {nuevo_estado.value.lower()}", "Reserva", reserva.id, f"{reserva.zona_comun}: {anterior} → {nuevo_estado.value}")
    if anterior != nuevo_estado.value and reserva.usuario_id != admin.id:
        notificar(db, [db.get(Usuario, reserva.usuario_id)], f"Tu reserva fue {nuevo_estado.value.lower()}",
                  f"{reserva.zona_comun} · {reserva.fecha_reserva:%d/%m/%Y %H:%M}", "#/reservas")
    db.commit()
    db.refresh(reserva)
    return _vista_reservas(db, [reserva])[0]


@router.patch("/reservas/{reserva_id}/cancelar", response_model=ReservaResponse, tags=[TAG_RESERVAS],
              summary="Cancelar mi propia reserva", description="El dueño de la reserva (o un administrador) puede cancelarla.",
              responses={404: {"description": "La reserva no existe"}, 403: {"description": "No es tu reserva"}})
def cancelar_reserva(reserva_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    reserva = db.get(Reserva, reserva_id)
    if reserva is None:
        raise HTTPException(status_code=404, detail="La reserva no existe.")
    if reserva.usuario_id != usuario.id and usuario.rol != ADMIN.value:
        raise HTTPException(status_code=403, detail="Solo puedes cancelar tus propias reservas.")
    reserva.estado = EstadoReserva.CANCELADA.value
    auditar(db, usuario, "Canceló reserva", "Reserva", reserva.id, reserva.zona_comun)
    db.commit()
    db.refresh(reserva)
    return _vista_reservas(db, [reserva])[0]


# =========================================================================
#                      MÓDULO DE REPORTES DE DAÑOS
# =========================================================================
TAG_DANIOS = "Gestión de Incidencias y Daños"


def procesar_reporte_en_segundo_plano(reporte_id: int, nombre_foto: str | None) -> None:
    """Tarea en segundo plano (BackgroundTasks): se ejecuta DESPUÉS de responder al cliente.

    Hoy solo registra un log. Es el punto donde se puede enchufar más adelante
    una notificación al administrador o un modelo de IA que analice la foto
    sin hacer esperar al residente.
    """
    logger.info("Nuevo reporte de daño #%s recibido (foto: %s)", reporte_id, nombre_foto)


@router.post("/mantenimiento/reportar-danio", response_model=ReporteResponse, status_code=status.HTTP_201_CREATED,
             tags=[TAG_DANIOS], summary="Reportar un daño (con foto opcional)",
             description="Roles: **Residente**, **Administrador**. Se envía como `multipart/form-data`. "
             "La foto debe ser una imagen real JPG, PNG o WEBP de máximo 5 MB; se guarda con un nombre aleatorio.",
             responses={400: {"description": "El archivo no es una imagen válida"}, 413: {"description": "Imagen demasiado grande"}})
async def crear_reporte_danio(
    background_tasks: BackgroundTasks,
    titulo: str = Form(..., min_length=5, max_length=100, description="Ej: Ascensor Torre 3 trabado"),
    descripcion: str = Form(..., min_length=10, max_length=1000, description="Detalle del daño observado"),
    archivo_foto: UploadFile | None = File(default=None, description="Foto del daño (JPG, PNG o WEBP)"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_roles(RESIDENTE, ADMIN)),
):
    nombre_foto = await guardar_imagen_validada(archivo_foto, con_miniatura=True) if archivo_foto and archivo_foto.filename else None

    nuevo = ReporteDanio(usuario_id=usuario.id, titulo=titulo, descripcion=descripcion,
                         foto_url=nombre_foto or "sin_foto.jpg", estado=EstadoDanio.ABIERTO.value)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)

    background_tasks.add_task(procesar_reporte_en_segundo_plano, nuevo.id, nombre_foto)
    return nuevo


@router.get("/mantenimiento/listar-danios", response_model=list[ReporteResponse], tags=[TAG_DANIOS],
            summary="Listar reportes de daños",
            description="**Administrador** ve todos; los demás roles ven solo los que ellos reportaron.")
def listar_danios(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    consulta = db.query(ReporteDanio)
    if usuario.rol != ADMIN.value:
        consulta = consulta.filter(ReporteDanio.usuario_id == usuario.id)
    return consulta.order_by(ReporteDanio.id.desc()).all()


@router.get("/mantenimiento/danios/{reporte_id}/foto", tags=[TAG_DANIOS], summary="Descargar la foto de un reporte",
            description="Solo el dueño del reporte o un **Administrador**. Las fotos NO son públicas.",
            responses={404: {"description": "Reporte o foto no encontrados"}, 403: {"description": "No es tu reporte"}})
def ver_foto_danio(reporte_id: int, miniatura: bool = False, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    reporte = db.get(ReporteDanio, reporte_id)
    if reporte is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    if reporte.usuario_id != usuario.id and usuario.rol != ADMIN.value:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver esta foto.")
    imagen = leer_imagen(reporte.foto_url, miniatura=miniatura) if reporte.foto_url and reporte.foto_url != "sin_foto.jpg" else None
    if imagen is None:
        raise HTTPException(status_code=404, detail="Este reporte no tiene foto.")
    return Response(content=imagen[0], media_type=imagen[1], headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})


@router.patch("/mantenimiento/cambiar-estado/{reporte_id}", response_model=ReporteResponse, tags=[TAG_DANIOS],
              summary="Actualizar el estado de un daño", description="Solo **Administrador**.",
              responses={404: {"description": "Reporte no encontrado"}})
def cambiar_estado_danio(reporte_id: int, nuevo_estado: EstadoDanio, db: Session = Depends(get_db),
                         admin: Usuario = Depends(requiere_roles(ADMIN))):
    reporte = db.get(ReporteDanio, reporte_id)
    if reporte is None:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    auditar(db, admin, "Cambió estado de daño", "Daño", reporte.id, f"{reporte.titulo}: {reporte.estado} → {nuevo_estado.value}")
    reporte.estado = nuevo_estado.value
    db.commit()
    db.refresh(reporte)
    return reporte


# =========================================================================
#                   MÓDULO DE RECAUDO DE ADMINISTRACIÓN
# =========================================================================
TAG_ADMIN = "Recaudo de Administración"


@router.get("/administracion/estado-cuenta/{usuario_id}", response_model=EstadoCuentaResponse, tags=[TAG_ADMIN],
            summary="Consultar estado de cuenta",
            description="Un residente solo puede consultar el suyo; el **Administrador** puede consultar el de cualquiera.",
            responses={403: {"description": "No es tu estado de cuenta"}, 404: {"description": "Usuario no encontrado"}})
def consultar_estado_cuenta(usuario_id: int, db: Session = Depends(get_db), actual: Usuario = Depends(get_current_user)):
    if usuario_id != actual.id and actual.rol != ADMIN.value:
        raise HTTPException(status_code=403, detail="Solo puedes consultar tu propio estado de cuenta.")
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return usuario


@router.patch("/administracion/registrar-deuda/{usuario_id}", response_model=EstadoCuentaResponse, tags=[TAG_ADMIN],
              summary="Registrar el saldo pendiente de un apartamento",
              description="Solo **Administrador**. Si el saldo es mayor a 0 el usuario queda **en mora** (no podrá reservar); "
              "si es 0 queda al día.", responses={404: {"description": "Usuario no encontrado"}})
def registrar_deuda(usuario_id: int, saldo_pendiente: int = Query(..., ge=0, examples=[300000]),
                    db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    auditar(db, admin, "Registró saldo", "Cartera", usuario.id, f"{usuario.nombre_completo}: ${usuario.saldo_pendiente} → ${saldo_pendiente}")
    usuario.saldo_pendiente = saldo_pendiente
    usuario.esta_al_dia = saldo_pendiente == 0
    db.commit()
    db.refresh(usuario)
    return usuario


def _aplicar_pago(db: Session, residente: Usuario, valor: int, actor: Usuario, accion: str, detalle_extra: str = "") -> dict:
    """Descuenta un pago del saldo, guarda el comprobante y deja la auditoría (todo en la misma transacción)."""
    if residente.saldo_pendiente <= 0:
        raise HTTPException(status_code=400, detail="No hay saldo pendiente por pagar.")
    if valor > residente.saldo_pendiente:
        raise HTTPException(status_code=400, detail=f"El valor excede el saldo pendiente (${residente.saldo_pendiente}).")

    auditar(db, actor, accion, "Cartera", residente.id,
            f"{residente.nombre_completo}: pago de ${valor}; saldo ${residente.saldo_pendiente - valor}{detalle_extra}")
    pago = Pago(usuario_id=residente.id, valor=valor, saldo_anterior=residente.saldo_pendiente, saldo_posterior=residente.saldo_pendiente - valor)
    db.add(pago)
    residente.saldo_pendiente -= valor
    residente.esta_al_dia = residente.saldo_pendiente == 0
    db.flush()
    return {"pago": pago}


@router.get("/administracion/config-pagos", tags=[TAG_ADMIN], summary="Cómo se paga en este conjunto",
            description="Roles: **todos**. Indica si el pago en línea es una simulación (demostración) o si se paga por transferencia "
            "y la administración registra el pago, junto con las instrucciones para el residente.")
def config_pagos(_: Usuario = Depends(get_current_user)):
    return {"pagos_simulados": config.PAGOS_SIMULADOS, "instrucciones": config.PAGOS_INSTRUCCIONES}


@router.post("/administracion/simular-pago-pasarela", response_model=PagoResponse, tags=[TAG_ADMIN],
             summary="Simular el pago de la administración (solo demostración)",
             description="Roles: **Residente**, **Administrador** (paga su propio saldo). Simula una pasarela de pagos: "
             "el valor debe ser mayor a 0 y no puede superar el saldo pendiente. Al llegar a 0 el apartamento queda al día. "
             "**Solo funciona si `PAGOS_SIMULADOS=1`**; en producción responde 403 y el pago lo registra el administrador.",
             responses={400: {"description": "Valor inválido o sin saldo pendiente"}, 403: {"description": "Los pagos simulados están desactivados"}})
def procesar_pago_pasarela(valor_pagado: int = Query(..., gt=0, examples=[150000]), db: Session = Depends(get_db),
                           usuario: Usuario = Depends(requiere_roles(RESIDENTE, ADMIN))):
    if not config.PAGOS_SIMULADOS:
        raise HTTPException(status_code=403, detail="El pago en línea aún no está habilitado. Paga por transferencia y la administración registrará tu pago.")
    pago = _aplicar_pago(db, usuario, valor_pagado, usuario, "Pagó administración")["pago"]
    db.commit()
    db.refresh(usuario)

    if usuario.esta_al_dia:
        mensaje = f"Pago recibido. El apartamento {usuario.apartamento} está al día y habilitado para reservas."
    else:
        mensaje = f"Pago parcial recibido. Saldo restante: ${usuario.saldo_pendiente}"
    return {"status": "Transacción Exitosa", "mensaje": mensaje, "saldo_pendiente": usuario.saldo_pendiente,
            "esta_al_dia": usuario.esta_al_dia, "pago_id": pago.id}


@router.post("/administracion/registrar-pago/{usuario_id}", response_model=PagoResponse, tags=[TAG_ADMIN],
             summary="Registrar un pago recibido (transferencia, efectivo)",
             description="Solo **Administrador**. Es la forma real de cobrar: el residente paga por fuera y el administrador registra el valor recibido. "
             "Descuenta del saldo, genera el comprobante `REC-…` y avisa al residente en su campana. `referencia` (opcional) es el número del "
             "comprobante bancario y queda en la auditoría.",
             responses={400: {"description": "Valor inválido o sin saldo pendiente"}, 404: {"description": "Usuario no encontrado"}})
def registrar_pago_recibido(usuario_id: int, valor_pagado: int = Query(..., gt=0, examples=[150000]),
                            referencia: Optional[str] = Query(None, max_length=60, examples=["Transf. 884213"]),
                            db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    residente = db.get(Usuario, usuario_id)
    if residente is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    extra = f" · ref. «{referencia.strip()}»" if referencia and referencia.strip() else ""
    pago = _aplicar_pago(db, residente, valor_pagado, admin, "Registró pago recibido", extra)["pago"]
    notificar(db, [residente], "Registramos tu pago de administración", f"${valor_pagado:,}".replace(",", ".") + ". Descarga tu comprobante en Mis pagos.", "#/cartera")
    db.commit()
    db.refresh(residente)
    mensaje = (f"Pago registrado. {residente.apartamento or residente.nombre_completo} quedó al día." if residente.esta_al_dia
               else f"Pago parcial registrado. Saldo restante: ${residente.saldo_pendiente}")
    return {"status": "Pago registrado", "mensaje": mensaje, "saldo_pendiente": residente.saldo_pendiente,
            "esta_al_dia": residente.esta_al_dia, "pago_id": pago.id}


@router.get("/administracion/mis-pagos", response_model=list[PagoRegistroResponse], tags=[TAG_ADMIN],
            summary="Ver mis pagos (con comprobante)",
            description="Roles: **Residente**, **Administrador**. Los últimos pagos registrados; de cada uno se puede descargar el comprobante en PDF "
                        "(`GET /reportes/recibo/{pago_id}.pdf`). El administrador puede ver los de otro usuario con `usuario_id`.")
def mis_pagos(usuario_id: Optional[int] = Query(None), limite: int = Query(24, ge=1, le=100), db: Session = Depends(get_db),
              usuario: Usuario = Depends(requiere_roles(RESIDENTE, ADMIN))):
    objetivo = usuario_id if (usuario_id and usuario.rol == ADMIN.value) else usuario.id
    pagos = db.query(Pago).filter(Pago.usuario_id == objetivo).order_by(Pago.id.desc()).limit(limite).all()
    return [PagoRegistroResponse(id=p.id, comprobante=f"REC-{p.fecha.year}-{p.id:06d}", valor=p.valor, saldo_anterior=p.saldo_anterior,
                                 saldo_posterior=p.saldo_posterior, fecha=p.fecha) for p in pagos]


# =========================================================================
#                   MÓDULO DE CONTROL DE PARQUEADEROS
# =========================================================================
TAG_PORTERIA = "Control de Parqueaderos"
PLACA_REGEX = r"^[A-Za-z]{3}[0-9]{2}[A-Za-z0-9]$"  # Carro: ABC123 · Moto: ABC12D


def ingresar_vehiculo(db: Session, personal: Usuario, placa: str, apartamento: str, cuando: Optional[datetime] = None) -> VehiculoVisitante:
    """Lógica de ingreso (sin commit). La reutiliza la sincronización de portería sin internet, donde `cuando` es la hora real del ingreso."""
    placa = placa.upper().strip()
    ya_dentro = db.query(VehiculoVisitante).filter(VehiculoVisitante.placa == placa, VehiculoVisitante.estado == "Dentro").first()
    if ya_dentro:
        raise HTTPException(status_code=400, detail=f"El vehículo {placa} ya figura dentro del conjunto.")
    vehiculo = VehiculoVisitante(placa=placa, apartamento_destino=apartamento, ingreso_registrado_por=personal.id)
    if cuando is not None:
        vehiculo.fecha_ingreso = cuando
    db.add(vehiculo)
    db.flush()
    return vehiculo


def sacar_vehiculo(db: Session, personal: Usuario, vehiculo: Optional[VehiculoVisitante], cuando: Optional[datetime] = None) -> VehiculoVisitante:
    if vehiculo is None:
        raise HTTPException(status_code=404, detail="Registro de vehículo no encontrado.")
    if vehiculo.estado == "Salido":
        raise HTTPException(status_code=400, detail="Este vehículo ya tiene registrada su salida.")
    vehiculo.fecha_salida = cuando or ahora_utc()
    vehiculo.estado = "Salido"
    vehiculo.salida_registrada_por = personal.id
    return vehiculo


@router.post("/porteria/vehiculo-ingreso", response_model=VehiculoResponse, status_code=status.HTTP_201_CREATED,
             tags=[TAG_PORTERIA], summary="Registrar el ingreso de un vehículo visitante",
             description="Roles: **Guardia**, **Administrador**. Formato de placa: `ABC123` (carro) o `ABC12D` (moto).",
             responses={400: {"description": "Ese vehículo ya está dentro del conjunto"}})
def registrar_ingreso_vehiculo(placa: str = Query(..., pattern=PLACA_REGEX, examples=["XYZ123"]),
                               apartamento: str = Query(..., min_length=1, max_length=50, examples=["Torre 1 Apt 202"]),
                               db: Session = Depends(get_db), personal: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    vehiculo = ingresar_vehiculo(db, personal, placa, apartamento)
    db.commit()
    db.refresh(vehiculo)
    return vehiculo


@router.patch("/porteria/vehiculo-salida/{vehiculo_id}", response_model=MensajeResponse, tags=[TAG_PORTERIA],
              summary="Registrar la salida de un vehículo", description="Roles: **Guardia**, **Administrador**.",
              responses={404: {"description": "Registro no encontrado"}, 400: {"description": "El vehículo ya salió"}})
def registrar_salida_vehiculo(vehiculo_id: int, db: Session = Depends(get_db),
                              personal: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    vehiculo = sacar_vehiculo(db, personal, db.get(VehiculoVisitante, vehiculo_id))
    db.commit()
    return {"mensaje": f"Salida confirmada para el vehículo {vehiculo.placa}."}


@router.get("/porteria/vehiculos-dentro", response_model=list[VehiculoResponse], tags=[TAG_PORTERIA],
            summary="Ver los vehículos que están dentro del conjunto", description="Roles: **Guardia**, **Administrador**.")
def vehiculos_dentro(db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    return db.query(VehiculoVisitante).filter(VehiculoVisitante.estado == "Dentro").order_by(VehiculoVisitante.fecha_ingreso).all()


# ---------------- HISTORIAL DE PORTERÍA ----------------
HORA_COLOMBIA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano


def _utc_sin_zona(dt: Optional[datetime]) -> Optional[datetime]:
    """Las fechas se guardan en UTC sin zona; si el cliente manda una con zona, se convierte."""
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _consulta_historial(db: Session, placa, apartamento, estado, desde, hasta):
    ing, sal = aliased(Usuario), aliased(Usuario)
    q = (db.query(VehiculoVisitante, ing.nombre_completo, sal.nombre_completo)
         .outerjoin(ing, VehiculoVisitante.ingreso_registrado_por == ing.id)
         .outerjoin(sal, VehiculoVisitante.salida_registrada_por == sal.id))
    if placa:
        q = q.filter(VehiculoVisitante.placa.contains(placa.upper().strip()))
    if apartamento:
        q = q.filter(VehiculoVisitante.apartamento_destino.ilike(f"%{apartamento.strip()}%"))
    if estado:
        q = q.filter(VehiculoVisitante.estado == estado)
    if desde:
        q = q.filter(VehiculoVisitante.fecha_ingreso >= _utc_sin_zona(desde))
    if hasta:
        q = q.filter(VehiculoVisitante.fecha_ingreso <= _utc_sin_zona(hasta))
    return q.order_by(VehiculoVisitante.fecha_ingreso.desc(), VehiculoVisitante.id.desc())


def _item_historial(v: VehiculoVisitante, quien_ingreso, quien_salida) -> VehiculoHistorialItem:
    duracion = int((v.fecha_salida - v.fecha_ingreso).total_seconds() // 60) if v.fecha_salida and v.fecha_ingreso else None
    return VehiculoHistorialItem(id=v.id, placa=v.placa, apartamento_destino=v.apartamento_destino, fecha_ingreso=v.fecha_ingreso,
                                 fecha_salida=v.fecha_salida, estado=v.estado, ingreso_registrado_por=quien_ingreso,
                                 salida_registrada_por=quien_salida, duracion_minutos=duracion)


@router.get("/porteria/historial", response_model=HistorialVehiculosResponse, tags=[TAG_PORTERIA],
            summary="Historial de ingresos y salidas de vehículos",
            description="Roles: **Guardia**, **Administrador**. Incluye hora de entrada, salida, duración y quién registró cada movimiento. "
                        "`desde` y `hasta` filtran por hora de ingreso; si traen zona horaria (ej. `...Z`) se convierten a UTC.")
def historial_vehiculos(placa: Optional[str] = Query(None, max_length=10), apartamento: Optional[str] = Query(None, max_length=50),
                        estado: Optional[str] = Query(None, pattern="^(Dentro|Salido)$"),
                        desde: Optional[datetime] = None, hasta: Optional[datetime] = None,
                        pagina: int = Query(1, ge=1), limite: int = Query(25, ge=1, le=200),
                        db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    q = _consulta_historial(db, placa, apartamento, estado, desde, hasta)
    total = q.order_by(None).count()
    filas = q.offset((pagina - 1) * limite).limit(limite).all()
    return HistorialVehiculosResponse(total=total, pagina=pagina, limite=limite, items=[_item_historial(*f) for f in filas])


def _celda_segura(valor) -> str:
    """Evita 'inyección de fórmulas' al abrir el CSV en Excel (textos que empiezan por = + - @)."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") else texto


@router.get("/porteria/historial/exportar", tags=[TAG_PORTERIA], summary="Exportar el historial a CSV (Excel)",
            description="Rol: **Administrador**. Mismos filtros que el historial; máximo 20.000 filas. Horas en hora de Colombia (UTC-5).",
            response_class=Response)
def exportar_historial(placa: Optional[str] = Query(None, max_length=10), apartamento: Optional[str] = Query(None, max_length=50),
                       estado: Optional[str] = Query(None, pattern="^(Dentro|Salido)$"),
                       desde: Optional[datetime] = None, hasta: Optional[datetime] = None,
                       db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(ADMIN))):
    filas = _consulta_historial(db, placa, apartamento, estado, desde, hasta).limit(20000).all()
    fmt = lambda d: d.replace(tzinfo=timezone.utc).astimezone(HORA_COLOMBIA).strftime("%Y-%m-%d %H:%M") if d else ""
    salida = io.StringIO()
    w = csv.writer(salida, delimiter=";")  # ';' es el separador que Excel en español espera
    w.writerow(["Placa", "Apartamento destino", "Ingreso (hora Colombia)", "Salida (hora Colombia)", "Duración (min)",
                "Estado", "Registró ingreso", "Registró salida"])
    for v, q_ing, q_sal in filas:
        item = _item_historial(v, q_ing, q_sal)
        w.writerow([_celda_segura(x) for x in [item.placa, item.apartamento_destino, fmt(item.fecha_ingreso), fmt(item.fecha_salida),
                                               item.duracion_minutos, item.estado, item.ingreso_registrado_por, item.salida_registrada_por]])
    nombre = f"historial_vehiculos_{datetime.now(HORA_COLOMBIA):%Y%m%d_%H%M}.csv"
    return Response(content="\ufeff" + salida.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
