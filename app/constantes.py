# app/constantes.py
# Valores permitidos para roles y estados. Al usar Enum, FastAPI los valida
# automáticamente y Swagger los muestra como lista desplegable.
from enum import Enum


class RolNombre(str, Enum):
    ADMINISTRADOR = "Administrador"
    RESIDENTE = "Residente"
    GUARDIA = "Guardia"
    INQUILINO = "Inquilino"   # vive en el apartamento por contrato con un propietario (Residente); permisos acotados


class EstadoReserva(str, Enum):
    PENDIENTE = "Pendiente"
    APROBADA = "Aprobada"
    CANCELADA = "Cancelada"


class EstadoDanio(str, Enum):
    ABIERTO = "Abierto"
    EN_REVISION = "En Revision"
    EN_REPARACION = "En Reparacion"
    SOLUCIONADO = "Solucionado"


class TipoAnuncio(str, Enum):
    REUNION = "Reunion"
    EVENTO = "Evento"
    AVISO = "Aviso"
    URGENTE = "Urgente"
    MANTENIMIENTO = "Mantenimiento"


DESCRIPCION_ROLES = {
    RolNombre.ADMINISTRADOR: "Gestiona usuarios, reservas, daños y cartera del conjunto",
    RolNombre.RESIDENTE: "Reserva zonas comunes, reporta daños y consulta su estado de cuenta",
    RolNombre.GUARDIA: "Controla el ingreso y salida de vehículos en portería",
    RolNombre.INQUILINO: "Vive en el apartamento por arrendamiento: reserva zonas, recibe paquetes y radica solicitudes; sin cartera ni votaciones",
}

# Quienes viven en el conjunto: el propietario (Residente) y su inquilino. Sirve para reglas como «ve solo lo suyo».
ROLES_RESIDENCIALES = (RolNombre.RESIDENTE.value, RolNombre.INQUILINO.value)


class EstadoArrendamiento(str, Enum):
    PENDIENTE = "Pendiente"      # lo registró el propietario; espera la aprobación del administrador (el inquilino aún no puede entrar)
    ACTIVO = "Activo"            # aprobado y dentro de las fechas del contrato
    FINALIZADO = "Finalizado"    # terminó por fecha, o lo cerró el propietario o el administrador
    RECHAZADO = "Rechazado"      # el administrador no lo aprobó


class Delegacion(str, Enum):
    """Lo que el propietario puede dejarle hacer a su inquilino (por defecto, nada de esto)."""
    PAGAR = "pagar"    # ver la cartera del apartamento y pagar la administración en nombre del propietario
    VOTAR = "votar"    # votar en las asambleas en nombre del apartamento


# Lo único que un inquilino puede ver de los documentos del conjunto (nada de actas ni de estados financieros).
CATEGORIAS_DOC_INQUILINO = ("Reglamento", "Circular")

# Tope de pases QR vigentes y de visitantes autorizados para un inquilino (el propietario conserva los topes normales).
MAX_VISITAS_INQUILINO = 5


# ---------- Fase 2: códigos QR ----------
class TipoQR(str, Enum):
    CARNET = "Carnet"        # identificación permanente del residente / personal
    VISITANTE = "Visitante"  # pase temporal con placa: ingreso y salida en portería


class EstadoQR(str, Enum):
    ACTIVO = "Activo"        # visitante: aún no ha ingresado
    DENTRO = "Dentro"        # visitante: ya ingresó, falta registrar la salida
    USADO = "Usado"          # visitante: ya entró y salió
    REVOCADO = "Revocado"    # anulado por el dueño o el administrador


# ---------- Fase 2: comercio (publicidad paga entre vecinos) ----------
class CategoriaComercio(str, Enum):
    COMIDA = "Comida"
    BELLEZA = "Belleza"
    HOGAR = "Hogar"
    SERVICIOS = "Servicios"
    MASCOTAS = "Mascotas"
    EDUCACION = "Educacion"
    OTROS = "Otros"


class PlanPublicidad(str, Enum):
    SEMANAL = "Semanal"
    MENSUAL = "Mensual"
    TRIMESTRAL = "Trimestral"


# Plan -> (días que dura el anuncio, valor en COP). Son valores de ejemplo: ajústalos a tu negocio.
PLANES_PUBLICIDAD = {
    PlanPublicidad.SEMANAL: (7, 15000),
    PlanPublicidad.MENSUAL: (30, 45000),
    PlanPublicidad.TRIMESTRAL: (90, 110000),
}


class EstadoPublicidad(str, Enum):
    PENDIENTE_PAGO = "Pendiente de pago"
    EN_REVISION = "En revision"      # el dueño informó el pago; el administrador debe confirmarlo
    ACTIVA = "Activa"
    RECHAZADA = "Rechazada"
    VENCIDA = "Vencida"


# ---------- Bloque 2: operación diaria ----------
class TipoVisitante(str, Enum):
    FAMILIAR = "Familiar"
    AMIGO = "Amigo"
    SERVICIO_DOMESTICO = "Servicio domestico"
    CUIDADOR = "Cuidador"
    CONTRATISTA = "Contratista"
    OTRO = "Otro"


class TipoPaquete(str, Enum):
    PAQUETE = "Paquete"
    CORRESPONDENCIA = "Correspondencia"
    DOMICILIO = "Domicilio"


class EstadoPaquete(str, Enum):
    EN_PORTERIA = "En porteria"   # llegó y espera a su dueño
    ENTREGADO = "Entregado"
    ANULADO = "Anulado"           # se registró por error (ej. apartamento equivocado)


class CategoriaEmergencia(str, Enum):
    EMERGENCIAS = "Emergencias"
    SALUD = "Salud"
    SEGURIDAD = "Seguridad"
    SERVICIOS = "Servicios publicos"
    ADMINISTRACION = "Administracion"
    OTROS = "Otros"


# ---------- Bloque 3: comunicación y reportes ----------
class TipoPQRS(str, Enum):
    PETICION = "Peticion"
    QUEJA = "Queja"
    RECLAMO = "Reclamo"
    SUGERENCIA = "Sugerencia"


class EstadoPQRS(str, Enum):
    RADICADA = "Radicada"        # el residente la envió; falta que la administración la lea
    EN_TRAMITE = "En tramite"
    RESUELTA = "Resuelta"        # ya tiene respuesta de la administración
    CERRADA = "Cerrada"


class CategoriaDocumento(str, Enum):
    REGLAMENTO = "Reglamento"
    ACTA = "Acta"
    CIRCULAR = "Circular"
    FINANCIERO = "Financiero"
    OTROS = "Otros"


# ---------- V3.8 · Fase 3 (legal y operativo): trasteos ----------
class TipoTrasteo(str, Enum):
    ENTRADA = "Entrada"    # llegan muebles al conjunto (mudanza de llegada)
    SALIDA = "Salida"      # salen muebles del conjunto: exige paz y salvo vigente


class EstadoTrasteo(str, Enum):
    PENDIENTE = "Pendiente"      # el residente lo solicitó; espera al administrador
    APROBADO = "Aprobado"        # el administrador lo aprobó y se avisó a portería
    EN_CURSO = "En curso"        # el guardia registró el inicio
    COMPLETADO = "Completado"    # el guardia registró el fin
    RECHAZADO = "Rechazado"
    CANCELADO = "Cancelado"
    # «Vencido» no se guarda: se calcula cuando una solicitud Pendiente/Aprobada pasó de fecha sin iniciarse.


MAX_TRASTEOS_ACTIVOS = 2          # solicitudes abiertas (pendientes, aprobadas o en curso) por apartamento
MAX_HORAS_TRASTEO = 12            # duración máxima de la ventana de un trasteo
MAX_DIAS_ANTICIPACION = 60        # no se puede pedir un trasteo para dentro de más de 60 días
HORAS_ANTES_PERMITIDAS = 2        # el guardia puede iniciar un trasteo hasta 2 h antes de la hora acordada


# ---------- V4.0 · Fase 4 (presentación comercial): solicitudes de demo ----------
class EstadoDemo(str, Enum):
    NUEVA = "Nueva"              # llegó desde la landing y nadie la ha atendido
    CONTACTADA = "Contactada"    # ya se habló con la persona
    AGENDADA = "Agendada"        # hay fecha para la demostración
    DESCARTADA = "Descartada"    # no avanzó (o era un envío de prueba)
