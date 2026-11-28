# app/routers/dashboard.py
# Indicadores para la pantalla «Indicadores» del administrador. TODO se calcula en la base de datos con consultas agregadas
# (COUNT / SUM / GROUP BY): el servidor devuelve ~1 KB de números en vez de miles de filas para que el navegador las cuente.
# Además se guarda 60 s en memoria: si el administrador abre y cierra la pantalla, o hay varios administradores, no se repite el cálculo.
import time
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.constantes import RolNombre
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import AccesoVisitante, Arrendamiento, Paquete, PQRS, ReporteDanio, Reserva, Rol, Usuario, VehiculoVisitante, ahora_utc
from app.schemas.dashboard import KPIsResponse

router = APIRouter(prefix="/dashboard", tags=["Indicadores (KPIs)"])
ADMIN = RolNombre.ADMINISTRADOR
HORA_COLOMBIA = timezone(timedelta(hours=-5))      # Colombia no tiene horario de verano
DIAS_RESERVAS, DIAS_PQRS, DIAS_VISITANTES = 90, 90, 30
VIGENCIA_CACHE_S = 60
_cache: dict = {}


def reiniciar_cache() -> None:
    _cache.clear()


def _calcular(db: Session) -> dict:
    ahora = ahora_utc()
    # --- cartera: una sola consulta
    unidades, al_dia, saldo = (db.query(func.count(Usuario.id), func.coalesce(func.sum(case((Usuario.esta_al_dia.is_(True), 1), else_=0)), 0),
                                        func.coalesce(func.sum(Usuario.saldo_pendiente), 0))
                               .join(Rol, Rol.id == Usuario.rol_id).filter(Rol.nombre == RolNombre.RESIDENTE.value, Usuario.esta_activo.is_(True)).one())
    cartera = {"unidades": unidades, "al_dia": int(al_dia), "en_mora": unidades - int(al_dia),
               "pct_al_dia": round(100 * int(al_dia) / unidades, 1) if unidades else 0.0, "saldo_total": int(saldo)}

    # --- reservas: las fechas de reserva están en hora local del conjunto (sin zona)
    ahora_local = ahora.replace(tzinfo=timezone.utc).astimezone(HORA_COLOMBIA).replace(tzinfo=None)
    zonas = (db.query(Reserva.zona_comun, func.count(Reserva.id)).filter(Reserva.estado == "Aprobada", Reserva.fecha_reserva >= ahora_local - timedelta(days=DIAS_RESERVAS))
             .group_by(Reserva.zona_comun).order_by(func.count(Reserva.id).desc(), Reserva.zona_comun).limit(8).all())
    pendientes = db.query(func.count(Reserva.id)).filter(Reserva.estado == "Pendiente").scalar()

    # --- PQRS: promedio de horas entre radicar y responder (solo las respondidas en la ventana). Lo calcula la base de datos:
    # «epoch» = segundos desde 1970, así la resta funciona igual en SQLite y en PostgreSQL (restar fechas directamente no es portable).
    desde = ahora - timedelta(days=DIAS_PQRS)
    respondidas, seg_promedio = (db.query(func.count(PQRS.id), func.avg(func.extract("epoch", PQRS.fecha_respuesta) - func.extract("epoch", PQRS.fecha_creacion)))
                                 .filter(PQRS.fecha_respuesta.isnot(None), PQRS.fecha_respuesta >= desde, PQRS.fecha_creacion.isnot(None),
                                         PQRS.fecha_respuesta >= PQRS.fecha_creacion).one())
    abiertas = db.query(func.count(PQRS.id)).filter(PQRS.estado.in_(["Radicada", "En tramite"])).scalar()

    # --- visitantes por hora local: la base agrupa por hora UTC (máximo 24 filas por tabla) y aquí solo se pasa a hora de Colombia
    desde_v = ahora - timedelta(days=DIAS_VISITANTES)
    por_hora = [0] * 24
    for modelo in (VehiculoVisitante, AccesoVisitante):
        hora = func.extract("hour", modelo.fecha_ingreso)
        for h, n in db.query(hora, func.count()).filter(modelo.fecha_ingreso >= desde_v).group_by(hora).all():
            por_hora[(int(h) - 5) % 24] += n          # UTC → hora de Colombia
    total_v = sum(por_hora)

    return {
        "generado": ahora.isoformat(), "cartera": cartera,
        "reservas": {"dias": DIAS_RESERVAS, "por_zona": [{"zona": z, "total": n} for z, n in zonas], "pendientes": pendientes},
        "pqrs": {"abiertas": abiertas, "respondidas": respondidas, "dias": DIAS_PQRS,
                 "horas_promedio_respuesta": round(float(seg_promedio) / 3600, 1) if respondidas and seg_promedio is not None else None},
        "visitantes": {"dias": DIAS_VISITANTES, "por_hora": por_hora, "total": total_v, "hora_pico": por_hora.index(max(por_hora)) if total_v else None},
        "operacion": {"vehiculos_dentro": db.query(func.count(VehiculoVisitante.id)).filter(VehiculoVisitante.estado == "Dentro").scalar(),
                      "paquetes_sin_entregar": db.query(func.count(Paquete.id)).filter(Paquete.estado == "En porteria").scalar(),
                      "danios_sin_resolver": db.query(func.count(ReporteDanio.id)).filter(ReporteDanio.estado != "Aprobado").scalar(),       # v5.7: «sin resolver» = todo lo que aún no cerró el administrador
                      "danios_por_aprobar": db.query(func.count(ReporteDanio.id)).filter(ReporteDanio.estado == "Solucionado").scalar(),
                      "arrendamientos_por_aprobar": db.query(func.count(Arrendamiento.id)).filter(Arrendamiento.estado == "Pendiente").scalar()},
    }


@router.get("/kpis", response_model=KPIsResponse, summary="Indicadores del conjunto",
            description="Solo **Administrador**. Cartera al día vs. en mora, zonas más reservadas (90 días), tiempo promedio de respuesta de PQRS (90 días) y flujo de visitantes por hora "
                        "(30 días, hora de Colombia). Se calcula con consultas agregadas y se guarda 60 s en memoria; `refrescar=true` fuerza el recálculo.")
def kpis(refrescar: bool = Query(False), db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(ADMIN))):
    vivo = _cache.get("kpis")
    if not refrescar and vivo and time.monotonic() - vivo[0] < VIGENCIA_CACHE_S:
        return vivo[1]
    datos = _calcular(db)
    _cache["kpis"] = (time.monotonic(), datos)
    return datos
