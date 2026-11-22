# app/models.py
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import relationship

from app.database import Base


def ahora_utc() -> datetime:
    """Fecha/hora UTC sin zona horaria (compatible con SQLite y PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==========================================
#               TABLA: ROLES
# ==========================================
class Rol(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, nullable=False)  # Administrador | Residente | Guardia
    descripcion = Column(String, nullable=True)

    usuarios = relationship("Usuario", back_populates="rol_rel")


# ==========================================
#             TABLA: USUARIOS
# ==========================================
class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre_completo = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_encriptada = Column(String, nullable=False)  # hash bcrypt

    # Llave foránea al rol (RBAC): define qué endpoints puede usar
    rol_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)   # se une en CADA petición autenticada (rol_rel lazy="joined")
    rol_rel = relationship("Rol", back_populates="usuarios", lazy="joined")

    apartamento = Column(String, nullable=True)
    esta_activo = Column(Boolean, default=True)

    # CANDADO FINANCIERO: True = al día / False = en mora
    esta_al_dia = Column(Boolean, default=True)
    valor_administracion = Column(Integer, default=150000)
    saldo_pendiente = Column(Integer, default=0)
    parqueadero_asignado = Column(String, default="Ninguno")
    # V3.8: coeficiente de copropiedad del apartamento, en PORCENTAJE (por ejemplo 0.8523 = 0,8523 %). Ley 675: pesa en votaciones de asamblea.
    coeficiente = Column(Float, nullable=True)

    # True cuando el administrador restableció la clave: la persona debe crear una propia al entrar.
    debe_cambiar_password = Column(Boolean, default=False, nullable=False)
    politica_datos_fecha = Column(DateTime, nullable=True)   # cuándo aceptó la política de tratamiento de datos

    @property
    def politica_aceptada(self) -> bool:
        return self.politica_datos_fecha is not None

    @property
    def rol(self) -> str:
        """Nombre del rol (ej: 'Administrador'). Mantiene el uso simple en el resto del código."""
        return self.rol_rel.nombre if self.rol_rel else ""


# ==========================================
#             TABLA: RESERVAS
# ==========================================
class Reserva(Base):
    __tablename__ = "reservas"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    zona_comun = Column(String, nullable=False)
    fecha_reserva = Column(DateTime, nullable=False, index=True)
    estado = Column(String, default="Pendiente", index=True)  # Pendiente | Aprobada | Cancelada
    fecha_creacion = Column(DateTime, default=ahora_utc)


# ==========================================
#          TABLA: REPORTES DE DAÑOS
# ==========================================
class ReporteDanio(Base):
    __tablename__ = "reportes_danios"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    titulo = Column(String, nullable=False)
    descripcion = Column(String, nullable=False)
    # Nombre del archivo guardado en la carpeta de uploads (nombre aleatorio, no el original)
    foto_url = Column(String, nullable=True, default="sin_foto.jpg")
    estado = Column(String, default="Abierto", index=True)  # Abierto | En Revision | En Reparacion | Solucionado
    fecha_creacion = Column(DateTime, default=ahora_utc)


# ==========================================
#       TABLA: VEHÍCULOS VISITANTES
# ==========================================
class VehiculoVisitante(Base):
    __tablename__ = "vehiculos_visitantes"

    id = Column(Integer, primary_key=True, index=True)
    placa = Column(String, nullable=False, index=True)
    apartamento_destino = Column(String, nullable=False)
    fecha_ingreso = Column(DateTime, default=ahora_utc, index=True)
    fecha_salida = Column(DateTime, nullable=True)
    estado = Column(String, default="Dentro", index=True)  # Dentro | Salido (se filtra en cada escaneo y en «vehículos dentro»)
    # Trazabilidad: qué miembro del personal registró cada movimiento (útil ante daños o reclamos).
    ingreso_registrado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    salida_registrada_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)


# ==========================================
#        TABLAS: ANUNCIOS Y ASISTENCIA
# ==========================================
class Anuncio(Base):
    __tablename__ = "anuncios"

    id = Column(Integer, primary_key=True, index=True)
    autor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    titulo = Column(String, nullable=False)
    contenido = Column(String, nullable=False)
    tipo = Column(String, nullable=False, default="Aviso")  # Reunion | Evento | Aviso | Urgente | Mantenimiento
    fecha_evento = Column(DateTime, nullable=True)           # hora local del conjunto, igual que las reservas
    lugar = Column(String, nullable=True)
    fijado = Column(Boolean, default=False, nullable=False)
    fecha_creacion = Column(DateTime, default=ahora_utc)


class AnuncioAsistencia(Base):
    __tablename__ = "anuncio_asistencias"
    __table_args__ = (UniqueConstraint("anuncio_id", "usuario_id", name="uq_asistencia_anuncio_usuario"),)

    id = Column(Integer, primary_key=True)
    anuncio_id = Column(Integer, ForeignKey("anuncios.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha = Column(DateTime, default=ahora_utc)


# ==========================================
#        FASE 2: CÓDIGOS QR Y ESCANEOS
# ==========================================
class CodigoQR(Base):
    """Cada QR guarda solo un token aleatorio e impredecible; lo que significa vive aquí, en la base de datos.
    Así un QR se puede revocar al instante y nunca expone datos personales."""
    __tablename__ = "codigos_qr"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)  # dueño del código
    tipo = Column(String, nullable=False)                    # Carnet | Visitante
    token = Column(String, unique=True, nullable=False, index=True)
    estado = Column(String, nullable=False, default="Activo")  # Activo | Dentro | Usado | Revocado
    nombre_visitante = Column(String, nullable=True)         # solo tipo Visitante
    placa = Column(String, nullable=True)                    # solo tipo Visitante
    valido_hasta = Column(DateTime, nullable=True)           # límite para INGRESAR (la salida siempre se permite)
    vehiculo_id = Column(Integer, ForeignKey("vehiculos_visitantes.id"), nullable=True)  # registro creado al ingresar
    fecha_creacion = Column(DateTime, default=ahora_utc)
    # v3.5 · PIN de 6 dígitos del pase (solo tipo Visitante): plan B cuando la cámara o la luz de la portería fallan.
    # Se guarda tal cual, igual que el token: la persona debe poder volver a verlo. Es único entre los pases VIGENTES (lo garantiza el código).
    pin = Column(String(6), nullable=True, index=True)
    # v3.5 · «Estoy en camino» / «Llegué» desde la página pública del pase: cuándo se avisó por última vez (para no repetir avisos en bucle).
    aviso_camino = Column(DateTime, nullable=True)
    aviso_llegada = Column(DateTime, nullable=True)


class EscaneoQR(Base):
    """Bitácora: quién escaneó qué y con qué resultado (también los intentos fallidos)."""
    __tablename__ = "escaneos_qr"

    id = Column(Integer, primary_key=True, index=True)
    codigo_id = Column(Integer, ForeignKey("codigos_qr.id"), nullable=True, index=True)  # NULL = código desconocido
    escaneado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    resultado = Column(String, nullable=False)   # Identidad verificada | Ingreso registrado | Salida registrada | Rechazado
    detalle = Column(String, nullable=True)
    fecha = Column(DateTime, default=ahora_utc, index=True)


# ==========================================
#        FASE 2: COMERCIO (PUBLICIDAD)
# ==========================================
class Publicidad(Base):
    __tablename__ = "publicidad"

    id = Column(Integer, primary_key=True, index=True)
    propietario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    nombre_negocio = Column(String, nullable=False)
    categoria = Column(String, nullable=False)
    titulo = Column(String, nullable=False)
    descripcion = Column(String, nullable=False)
    precio_texto = Column(String, nullable=True)             # ej. "Desde $12.000"
    whatsapp = Column(String, nullable=False)                # celular colombiano de 10 dígitos
    imagen = Column(String, nullable=True)                   # nombre del archivo en uploads/
    plan = Column(String, nullable=False)
    valor = Column(Integer, nullable=False)                  # lo que se cobra por el plan (COP)
    estado = Column(String, nullable=False, default="Pendiente de pago", index=True)
    referencia_pago = Column(String, nullable=True)          # comprobante que informa el dueño
    motivo_rechazo = Column(String, nullable=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    contactos = Column(Integer, nullable=False, default=0)   # veces que alguien tocó «Escribir por WhatsApp»
    revisado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)


# ==========================================
#        BLOQUE 1: SEGURIDAD Y AUDITORÍA
# ==========================================
class Auditoria(Base):
    """Quién (actor) hizo qué (accion) sobre qué (entidad + id) y cuándo."""
    __tablename__ = "auditoria"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)   # NULL = sistema / intento sin sesión
    accion = Column(String, nullable=False)
    entidad = Column(String, nullable=False, index=True)    # Reserva | Usuario | Cartera | Daño | Anuncio | Comercio | Seguridad
    entidad_id = Column(Integer, nullable=True)
    detalle = Column(String, nullable=True)
    fecha = Column(DateTime, default=ahora_utc, index=True)


class IntentoLogin(Base):
    """Cuenta los fallos de inicio de sesión por correo escrito (exista o no, para no revelar qué correos hay)."""
    __tablename__ = "intentos_login"

    id = Column(Integer, primary_key=True, index=True)
    clave = Column(String, unique=True, index=True, nullable=False)   # correo en minúsculas
    fallos = Column(Integer, nullable=False, default=0)
    ultimo_intento = Column(DateTime, default=ahora_utc)
    bloqueado_hasta = Column(DateTime, nullable=True)


# ==========================================
#        BLOQUE 2: OPERACIÓN DIARIA
# ==========================================
class VisitanteAutorizado(Base):
    """Persona que el residente deja autorizada de forma recurrente (familia, empleada, cuidador...).
    Nunca se borra: al «retirarla» queda inactiva para conservar el historial de ingresos."""
    __tablename__ = "visitantes_autorizados"
    __table_args__ = (UniqueConstraint("usuario_id", "documento", name="uq_visitante_usuario_documento"),)

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)   # residente que la autoriza
    nombre = Column(String, nullable=False)
    documento = Column(String, nullable=False, index=True)   # cédula / pasaporte, solo letras y números
    tipo = Column(String, nullable=False, default="Otro")
    vigente_hasta = Column(DateTime, nullable=True)           # NULL = sin vencimiento (hora local del conjunto)
    notas = Column(String, nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)


class AccesoVisitante(Base):
    """Cada entrada (y salida) a pie de un visitante autorizado, con el guardia que la registró."""
    __tablename__ = "accesos_visitantes"

    id = Column(Integer, primary_key=True, index=True)
    visitante_id = Column(Integer, ForeignKey("visitantes_autorizados.id"), nullable=False, index=True)
    fecha_ingreso = Column(DateTime, default=ahora_utc, index=True)
    fecha_salida = Column(DateTime, nullable=True)
    ingreso_registrado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    salida_registrada_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)


class Paquete(Base):
    """Paquetes y correspondencia que llegan a portería para un residente."""
    __tablename__ = "paquetes"

    id = Column(Integer, primary_key=True, index=True)
    destinatario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo = Column(String, nullable=False, default="Paquete")
    remitente = Column(String, nullable=True)                 # empresa o mensajero, ej. "Servientrega"
    descripcion = Column(String, nullable=True)               # ej. "Caja mediana, frágil"
    estado = Column(String, nullable=False, default="En porteria", index=True)
    recibido_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)    # quién lo recibió en portería
    fecha_recepcion = Column(DateTime, default=ahora_utc, index=True)
    entregado_a = Column(String, nullable=True)               # nombre de quien lo recogió
    entregado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)   # quién lo entregó
    fecha_entrega = Column(DateTime, nullable=True)
    foto_url = Column(String, nullable=True)                  # nombre del archivo de la foto del paquete (opcional, como evidencia)


class ContactoEmergencia(Base):
    """Directorio de emergencias del conjunto: lo administra el administrador y lo ven todos."""
    __tablename__ = "contactos_emergencia"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    telefono = Column(String, nullable=False)
    categoria = Column(String, nullable=False, default="Otros")
    descripcion = Column(String, nullable=True)
    orden = Column(Integer, nullable=False, default=0)
    fecha_creacion = Column(DateTime, default=ahora_utc)


# ==========================================
#   BLOQUE 3: COMUNICACIÓN Y REPORTES
# ==========================================
class Notificacion(Base):
    """Aviso dentro de la app (la campana): un paquete llegó, respondieron tu PQRS, hay un anuncio nuevo..."""
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    titulo = Column(String, nullable=False)
    mensaje = Column(String, nullable=True)
    enlace = Column(String, nullable=True)            # ruta de la app, ej. "#/paquetes"
    leida = Column(Boolean, nullable=False, default=False, index=True)
    fecha = Column(DateTime, default=ahora_utc, index=True)


class PQRS(Base):
    """Petición, queja, reclamo o sugerencia de un residente a la administración."""
    __tablename__ = "pqrs"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo = Column(String, nullable=False)             # Peticion | Queja | Reclamo | Sugerencia
    asunto = Column(String, nullable=False)
    descripcion = Column(String, nullable=False)
    estado = Column(String, nullable=False, default="Radicada", index=True)   # Radicada | En tramite | Resuelta | Cerrada
    respuesta = Column(String, nullable=True)
    respondido_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_respuesta = Column(DateTime, nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc, index=True)
    fecha_actualizacion = Column(DateTime, default=ahora_utc, onupdate=ahora_utc)


class Documento(Base):
    """PDF del conjunto (reglamento, actas, circulares) que sube el administrador y descargan todos."""
    __tablename__ = "documentos"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String, nullable=False)
    categoria = Column(String, nullable=False, default="Otros")
    descripcion = Column(String, nullable=True)
    archivo = Column(String, nullable=False)          # nombre aleatorio guardado en uploads/documentos/
    nombre_original = Column(String, nullable=False)
    tamano = Column(Integer, nullable=False, default=0)   # bytes
    subido_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc, index=True)


class Pago(Base):
    """Pago de administración registrado (genera un comprobante descargable)."""
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    valor = Column(Integer, nullable=False)
    saldo_anterior = Column(Integer, nullable=False)
    saldo_posterior = Column(Integer, nullable=False)
    fecha = Column(DateTime, default=ahora_utc, index=True)


# ==========================================
#   VERSIÓN 2.9: ASISTENTE DE IA
# ==========================================
class UsoAsistente(Base):
    """Una fila por consulta al asistente de IA. Sirve para los topes diarios (por persona y global). NO guarda el texto escrito."""
    __tablename__ = "uso_asistente"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    funcion = Column(String, nullable=False)           # residente | anuncio | chat (v3.2)
    fecha = Column(DateTime, default=ahora_utc, index=True)


# ==========================================
#   VERSIÓN 3.1: SESIONES SEGURAS
# ==========================================
class Sesion(Base):
    """Una fila por dispositivo con la sesión abierta. Guarda solo el HASH del token de renovación (refresh), nunca el token.
    Se rota en cada uso; si alguien reutiliza uno viejo (robo), toda la sesión se revoca. Revocar = cerrar sesión desde el servidor."""
    __tablename__ = "sesiones"

    id = Column(String(32), primary_key=True)                 # uuid hex; también va dentro del JWT como «sid»
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    token_anterior_hash = Column(String(64), nullable=True, index=True)   # el inmediatamente anterior (detecta reutilización)
    rotado_en = Column(DateTime, nullable=True)
    creada = Column(DateTime, default=ahora_utc)
    ultimo_uso = Column(DateTime, default=ahora_utc)
    expira = Column(DateTime, nullable=False)                 # vencimiento «deslizante»: se corre con el uso
    maxima = Column(DateTime, nullable=False)                 # vencimiento absoluto: no se corre nunca
    revocada = Column(DateTime, nullable=True)
    dispositivo = Column(String(120), nullable=True)
    ip = Column(String(45), nullable=True)


# ==========================================
#   VERSIÓN 3.1: AVISOS PUSH
# ==========================================
class SuscripcionPush(Base):
    """Un navegador/celular que aceptó recibir avisos aunque la app esté cerrada."""
    __tablename__ = "suscripciones_push"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    endpoint = Column(String, unique=True, nullable=False, index=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    dispositivo = Column(String(120), nullable=True)
    creada = Column(DateTime, default=ahora_utc)
    ultimo_exito = Column(DateTime, nullable=True)
    fallos = Column(Integer, nullable=False, default=0)


# ==========================================
#   VERSIÓN 3.1: VOTACIONES
# ==========================================
class Votacion(Base):
    """Consulta o votación del conjunto. Voto SECRETO: quién votó (Participacion) y qué se votó (conteo de cada opción) se guardan
    por separado y no hay forma de unirlos."""
    __tablename__ = "votaciones"

    id = Column(Integer, primary_key=True, index=True)
    autor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    titulo = Column(String, nullable=False)
    descripcion = Column(String, nullable=True)
    estado = Column(String, nullable=False, default="Abierta", index=True)    # Abierta | Cerrada | Anulada (vence sola con fecha_cierre)
    fecha_inicio = Column(DateTime, default=ahora_utc)
    fecha_cierre = Column(DateTime, nullable=False)           # UTC
    un_voto_por = Column(String, nullable=False, default="apartamento")      # apartamento | persona
    resultados_en_vivo = Column(Boolean, nullable=False, default=False)
    exige_al_dia = Column(Boolean, nullable=False, default=False)             # solo vota quien está al día con la administración
    ponderada = Column(Boolean, nullable=False, default=False)                # V3.8: cada voto vale el coeficiente de copropiedad del apartamento (Ley 675)
    cerrada_en = Column(DateTime, nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)


class VotacionOpcion(Base):
    __tablename__ = "votacion_opciones"

    id = Column(Integer, primary_key=True)
    votacion_id = Column(Integer, ForeignKey("votaciones.id"), nullable=False, index=True)
    texto = Column(String, nullable=False)
    orden = Column(Integer, nullable=False, default=0)
    conteo = Column(Integer, nullable=False, default=0)
    peso = Column(Float, nullable=False, default=0.0)         # V3.8: suma de los coeficientes (%) de quienes eligieron esta opción (solo votaciones ponderadas)


class VotacionParticipacion(Base):
    """Quién ya votó (no qué votó). La restricción única impide votar dos veces aunque lleguen dos peticiones a la vez."""
    __tablename__ = "votacion_participaciones"
    __table_args__ = (UniqueConstraint("votacion_id", "clave", name="uq_participacion_votacion_clave"),)

    id = Column(Integer, primary_key=True)
    votacion_id = Column(Integer, ForeignKey("votaciones.id"), nullable=False, index=True)
    clave = Column(String, nullable=False)                    # «apto:torre 1 apt 101» o «usr:15»
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    peso = Column(Float, nullable=False, default=0.0)         # V3.8: coeficiente (%) con el que votó ese apartamento; sirve para el quórum. No dice QUÉ votó.
    fecha = Column(DateTime, default=ahora_utc)


# ==========================================
#   VERSIÓN 3.1: PORTERÍA SIN INTERNET
# ==========================================
class OperacionOffline(Base):
    """Registro de cada operación que la portería hizo sin conexión y luego sincronizó. El `uuid` lo genera el celular:
    si la sincronización se repite (se cortó la red a mitad), la operación NO se duplica."""
    __tablename__ = "operaciones_offline"
    __table_args__ = (UniqueConstraint("usuario_id", "uuid", name="uq_operacion_usuario_uuid"),)

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    uuid = Column(String(64), nullable=False)
    tipo = Column(String, nullable=False)
    ok = Column(Boolean, nullable=False, default=True)
    resultado = Column(String, nullable=True)                 # JSON con el id creado, o el motivo del rechazo
    fecha = Column(DateTime, default=ahora_utc, index=True)


# Índices compuestos para las consultas más frecuentes (la campana, la lista de paquetes y «vehículos dentro»).
Index("ix_notificaciones_usuario_leida", Notificacion.usuario_id, Notificacion.leida)
Index("ix_paquetes_destinatario_estado", Paquete.destinatario_id, Paquete.estado)
Index("ix_vehiculos_estado", VehiculoVisitante.estado)
Index("ix_accesos_visitantes_salida", AccesoVisitante.fecha_salida)


# ==========================================
#          TABLA: ARRENDAMIENTOS
# ==========================================
class Arrendamiento(Base):
    """Vínculo entre el propietario (Residente), su inquilino y el apartamento.
    De aquí salen tres reglas: la mora del apartamento la hereda el inquilino, el acceso vence con el contrato y queda
    registrado quién autorizó a quién."""
    __tablename__ = "arrendamientos"
    __table_args__ = (Index("ix_arrendamientos_propietario_estado", "propietario_id", "estado"),)

    id = Column(Integer, primary_key=True, index=True)
    propietario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    inquilino_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    apartamento = Column(String, nullable=True)
    fecha_inicio = Column(DateTime, nullable=False)
    fecha_fin = Column(DateTime, nullable=False)              # el acceso se cierra al terminar este día (hora local del conjunto)
    estado = Column(String, nullable=False, default="Pendiente")   # Pendiente | Activo | Finalizado | Rechazado
    puede_pagar = Column(Boolean, nullable=False, default=False)   # delegación del propietario: cartera y pagos del apartamento
    puede_votar = Column(Boolean, nullable=False, default=False)   # delegación del propietario: voto del apartamento
    motivo_cierre = Column(String, nullable=True)
    aprobado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)
    fecha_decision = Column(DateTime, nullable=True)

    propietario = relationship("Usuario", foreign_keys=[propietario_id])
    inquilino = relationship("Usuario", foreign_keys=[inquilino_id])


# ==========================================
#   V3.6 · PAZ Y SALVO CON QR DE VERIFICACIÓN
# ==========================================
class PazSalvo(Base):
    """Certificado de paz y salvo con código único. El QR del PDF apunta a /verificar/<codigo>: cualquiera (banco, empresa de trasteos, guardia)
    comprueba en el servidor que es auténtico y sigue vigente. «Vigente» no se guarda: se calcula (no revocado, no vencido y el apartamento sigue al día)."""
    __tablename__ = "paz_y_salvos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)   # el titular (propietario) del apartamento
    codigo = Column(String, unique=True, nullable=False, index=True)                       # aleatorio de 128 bits: es lo que viaja en el QR
    destino = Column(String(80), nullable=True)                                            # para qué se pidió: «Mudanza», «Trámite bancario»…
    fecha_emision = Column(DateTime, default=ahora_utc, nullable=False, index=True)
    valido_hasta = Column(DateTime, nullable=False)
    emitido_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)               # quién lo pidió (puede ser el inquilino con permiso, o el administrador)
    revocado = Column(Boolean, nullable=False, default=False)


# ==========================================
#   V3.8 · TRASTEOS (mudanzas) CON VALIDACIÓN DE PAZ Y SALVO
# ==========================================
class Trasteo(Base):
    """Solicitud de trasteo: la pide el residente (o su inquilino), la aprueba el administrador y la ejecuta la portería.
    Una SALIDA solo se aprueba y se inicia si el apartamento tiene paz y salvo vigente (se vuelve a comprobar en cada paso)."""
    __tablename__ = "trasteos"
    __table_args__ = (Index("ix_trasteos_estado_inicio", "estado", "fecha_inicio"),)

    id = Column(Integer, primary_key=True, index=True)
    solicitante_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    titular_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)    # el propietario del apartamento (de quien se valida el paz y salvo)
    apartamento = Column(String, nullable=True)
    tipo = Column(String, nullable=False)                      # Entrada | Salida
    fecha_inicio = Column(DateTime, nullable=False)            # UTC: desde cuándo puede entrar/salir el trasteo
    fecha_fin = Column(DateTime, nullable=False)               # UTC: hasta cuándo
    empresa = Column(String(80), nullable=True)                # empresa de trasteos o nombre de quien lo hace
    placa = Column(String(15), nullable=True)                  # placa del camión o vehículo
    observaciones = Column(String(300), nullable=True)
    estado = Column(String, nullable=False, default="Pendiente")
    paz_salvo_id = Column(Integer, ForeignKey("paz_y_salvos.id"), nullable=True)           # el certificado con el que se pidió (solo Salida)
    decidido_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_decision = Column(DateTime, nullable=True)
    motivo = Column(String(200), nullable=True)                # motivo del rechazo o de la cancelación
    registrado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)             # el guardia que lo inició
    inicio_real = Column(DateTime, nullable=True)
    fin_real = Column(DateTime, nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)


# ==========================================
#   V4.0 · PRESENTACIÓN COMERCIAL: SOLICITUDES DE DEMO
# ==========================================
class SolicitudDemo(Base):
    """Contacto que dejó alguien en la landing («Solicitar demo») o que tocó «Escribir por WhatsApp». Lo ve y lo gestiona el administrador.
    No guarda la IP ni nada del dispositivo: solo lo que la persona escribió y que autorizó el tratamiento de sus datos (Ley 1581 de 2012)."""
    __tablename__ = "solicitudes_demo"
    __table_args__ = (Index("ix_solicitudes_demo_estado_fecha", "estado", "fecha_creacion"),)

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(80), nullable=False)
    conjunto = Column(String(100), nullable=False)            # nombre del conjunto o de la administradora
    celular = Column(String(15), nullable=False, index=True)  # solo dígitos
    correo = Column(String(120), nullable=True)
    ciudad = Column(String(60), nullable=True)
    apartamentos = Column(Integer, nullable=True)             # cuántas unidades tiene (sirve para dimensionar la propuesta)
    mensaje = Column(String(500), nullable=True)
    origen = Column(String(12), nullable=False, default="formulario")   # formulario | whatsapp
    estado = Column(String(12), nullable=False, default="Nueva", index=True)   # Nueva | Contactada | Agendada | Descartada
    nota = Column(String(300), nullable=True)                 # seguimiento interno del administrador
    acepto_datos = Column(DateTime, nullable=False, default=ahora_utc)
    fecha_creacion = Column(DateTime, default=ahora_utc, nullable=False, index=True)
    fecha_actualizacion = Column(DateTime, default=ahora_utc, onupdate=ahora_utc)


# ==========================================
#   V4.2 · PASARELA DE PAGOS SIMULADA (tipo Wompi / PSE)
# ==========================================
class IntentoPago(Base):
    """Un intento de pago en la pasarela de PRUEBAS (solo con PAGOS_SIMULADOS=1). Imita el recorrido de una pasarela real: la app crea el intento
    (referencia), la pasarela decide el resultado y, si lo aprueba, recién ahí se descuenta del saldo. NUNCA guarda datos de tarjeta, documento ni celular."""
    __tablename__ = "intentos_pago"

    id = Column(Integer, primary_key=True, index=True)
    referencia = Column(String(24), nullable=False, unique=True, index=True)          # SIM-XXXXXXXXXX
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)   # quien paga (el propietario o su inquilino con permiso)
    titular_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)               # dueño de la deuda
    valor = Column(Integer, nullable=False)
    metodo = Column(String(10), nullable=True)                                            # PSE | Tarjeta | Nequi (se fija al pagar)
    estado = Column(String(10), nullable=False, default="Creado", index=True)             # Creado | Pendiente | Aprobado | Rechazado | Expirado
    mensaje = Column(String(200), nullable=True)                                          # lo que «dijo» la pasarela
    pago_id = Column(Integer, ForeignKey("pagos.id"), nullable=True)                      # el pago real que quedó registrado si fue aprobado
    resuelve_en = Column(DateTime, nullable=True)                                         # si quedó «Pendiente»: cuándo llega la confirmación
    fecha_creacion = Column(DateTime, default=ahora_utc, nullable=False)
    fecha_resolucion = Column(DateTime, nullable=True)



# ==========================================
#   V4.6 · ASAMBLEAS DE COPROPIETARIOS (Ley 675 de 2001)
# ==========================================
class Unidad(Base):
    """Una unidad privada (apartamento) del conjunto con su coeficiente de copropiedad. Es la BASE del quórum: el 100 % del conjunto,
    incluso los propietarios que no tienen cuenta en la app. Las unidades con residentes en la app se mantienen solas a partir de «Usuarios»;
    las demás (propietarios sin cuenta) las registra el administrador a mano."""
    __tablename__ = "unidades"

    id = Column(Integer, primary_key=True, index=True)
    apartamento = Column(String, nullable=False)                      # como se muestra: «Torre 1 Apt 101»
    clave = Column(String, nullable=False, unique=True, index=True)   # apartamento normalizado (sin tildes, mayúsculas ni espacios de más)
    coeficiente = Column(Float, nullable=True)                        # en PORCENTAJE (0,8523 = 0,8523 %)
    propietario_nombre = Column(String(120), nullable=True)
    origen = Column(String(10), nullable=False, default="usuarios")   # usuarios | manual
    activa = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)
    fecha_actualizacion = Column(DateTime, default=ahora_utc, onupdate=ahora_utc)


class Asamblea(Base):
    """Una reunión de la asamblea general de copropietarios. Envuelve el registro de asistentes, poderes, quórum y la bitácora de evidencia."""
    __tablename__ = "asambleas"
    __table_args__ = (Index("ix_asambleas_estado_fecha", "estado", "fecha_sesion"),)

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(120), nullable=False)
    tipo = Column(String(15), nullable=False)                         # Ordinaria | Extraordinaria
    modalidad = Column(String(10), nullable=False)                    # Presencial | Virtual | Mixta
    estado = Column(String(10), nullable=False, default="Borrador")
    orden_del_dia = Column(Text, nullable=False)
    fecha_sesion = Column(DateTime, nullable=False)                   # UTC: primera convocatoria
    fecha_segunda = Column(DateTime, nullable=False)                  # UTC: segunda convocatoria (Art. 41: tercer día hábil siguiente, 8 p. m.)
    lugar = Column(String(150), nullable=True)
    url_videollamada = Column(String(300), nullable=True)
    instrucciones_virtual = Column(String(500), nullable=True)        # medios tecnológicos que se usarán (los exige el Decreto 398 de 2020)
    max_poderes = Column(Integer, nullable=False, default=2)
    restringe_mora = Column(Boolean, nullable=False, default=False)   # el reglamento le quita el voto a quien está en mora
    # --- se llenan al convocar ---
    fecha_convocatoria = Column(DateTime, nullable=True)
    convocatoria_hash = Column(String(64), nullable=True)             # huella (SHA-256) del contenido exacto que se envió
    morosos_snapshot = Column(Text, nullable=True)                    # JSON: relación de morosos al momento de convocar (Art. 39, parágrafo 2)
    # --- se llenan en la sesión ---
    sin_quorum_en = Column(DateTime, nullable=True)                   # la 1.ª convocatoria no logró quórum
    convocatoria_numero = Column(Integer, nullable=True)              # 1 | 2: con cuál se instaló
    instalada_en = Column(DateTime, nullable=True)
    quorum_inicial = Column(Float, nullable=True)                     # % del coeficiente presente al instalar
    cerrada_en = Column(DateTime, nullable=True)
    quorum_final = Column(Float, nullable=True)
    creada_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)
    fecha_actualizacion = Column(DateTime, default=ahora_utc, onupdate=ahora_utc)


class AsambleaDocumento(Base):
    """Documentos (estados financieros, informe de gestión, propuesta de presupuesto) que acompañan la convocatoria."""
    __tablename__ = "asamblea_documentos"
    __table_args__ = (UniqueConstraint("asamblea_id", "documento_id", name="uq_asamblea_documento"),)

    id = Column(Integer, primary_key=True, index=True)
    asamblea_id = Column(Integer, ForeignKey("asambleas.id"), nullable=False, index=True)
    documento_id = Column(Integer, ForeignKey("documentos.id"), nullable=False)


class AsambleaEvento(Base):
    """Bitácora de evidencia: solo se agregan filas (nunca se editan ni se borran desde la app). Cada una guarda la huella de la anterior, así
    cualquier alteración posterior rompe la cadena y se detecta al verificarla."""
    __tablename__ = "asamblea_eventos"
    __table_args__ = (UniqueConstraint("asamblea_id", "secuencia", name="uq_asamblea_evento_secuencia"),)

    id = Column(Integer, primary_key=True, index=True)
    asamblea_id = Column(Integer, ForeignKey("asambleas.id"), nullable=False, index=True)
    secuencia = Column(Integer, nullable=False)
    tipo = Column(String(30), nullable=False)
    unidad_id = Column(Integer, ForeignKey("unidades.id"), nullable=True)
    actor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    detalle = Column(String(300), nullable=True)
    creado_en = Column(DateTime, nullable=False)
    hash_anterior = Column(String(64), nullable=False)
    hash = Column(String(64), nullable=False)


class AsambleaPoder(Base):
    """Poder escrito con el que un propietario autoriza a otra persona a representarlo en una asamblea."""
    __tablename__ = "asamblea_poderes"
    __table_args__ = (Index("ix_asamblea_poderes_asamblea_unidad", "asamblea_id", "unidad_id"),)

    id = Column(Integer, primary_key=True, index=True)
    asamblea_id = Column(Integer, ForeignKey("asambleas.id"), nullable=False, index=True)
    unidad_id = Column(Integer, ForeignKey("unidades.id"), nullable=False)
    apoderado_nombre = Column(String(120), nullable=False)
    apoderado_documento = Column(String(30), nullable=False)          # solo dígitos y letras, sin puntos ni espacios
    apoderado_usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)   # si el apoderado tiene cuenta (lo vincula el administrador)
    archivo = Column(String(80), nullable=False)
    tipo_archivo = Column(String(6), nullable=False)                  # pdf | imagen
    estado = Column(String(10), nullable=False, default="Pendiente")
    motivo = Column(String(200), nullable=True)                       # por qué se rechazó
    subido_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    revisado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    revisado_en = Column(DateTime, nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)


class AsambleaAsistente(Base):
    """Quién está (o estuvo) en la asamblea por cada unidad. Es UNA fila por unidad: si la persona sale y vuelve, la fila se reabre y la bitácora
    guarda cada movimiento. El coeficiente se COPIA al acreditar (una «foto»), para que un cambio posterior no altere el quórum de esa reunión."""
    __tablename__ = "asamblea_asistentes"
    __table_args__ = (UniqueConstraint("asamblea_id", "unidad_id", name="uq_asamblea_asistente_unidad"),)

    id = Column(Integer, primary_key=True, index=True)
    asamblea_id = Column(Integer, ForeignKey("asambleas.id"), nullable=False, index=True)
    unidad_id = Column(Integer, ForeignKey("unidades.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)   # la cuenta de quien entró, si la tiene
    nombre = Column(String(120), nullable=False)
    documento = Column(String(30), nullable=True)
    es_apoderado = Column(Boolean, nullable=False, default=False)
    poder_id = Column(Integer, ForeignKey("asamblea_poderes.id"), nullable=True)
    modalidad_ingreso = Column(String(10), nullable=False, default="Presencial")
    hora_ingreso = Column(DateTime, nullable=False)                   # del ingreso más reciente
    hora_salida = Column(DateTime, nullable=True)                     # vacío = sigue presente
    coeficiente_acreditado = Column(Float, nullable=False)
    en_mora = Column(Boolean, nullable=False, default=False)
    con_voto = Column(Boolean, nullable=False, default=True)
    registrado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)


# ==========================================
#   V5.2 · VOTACIONES DENTRO DE LA ASAMBLEA (Ley 675 de 2001)
# ==========================================
class AsambleaVotacion(Base):
    """Una pregunta que se vota dentro de una asamblea (punto del orden del día). Es independiente del motor de «Votaciones» del conjunto: allí se
    vota por apartamentos con cuenta; aquí se vota por UNIDAD acreditada, con el coeficiente «fotografiado» y con el quórum validado por pregunta.
    Al abrirla se guarda el padrón (quiénes pueden votar, con su coeficiente); al cerrarla se congela el resultado con su huella SHA-256."""
    __tablename__ = "asamblea_votaciones"
    __table_args__ = (
        UniqueConstraint("asamblea_id", "numero", name="uq_asamblea_votacion_numero"),
        # Solo UNA votación abierta por asamblea, garantizado por la base de datos y no solo por el código.
        Index("uq_asamblea_votacion_una_abierta", "asamblea_id", unique=True, sqlite_where=text("estado = 'Abierta'"), postgresql_where=text("estado = 'Abierta'")),
    )

    id = Column(Integer, primary_key=True, index=True)
    asamblea_id = Column(Integer, ForeignKey("asambleas.id"), nullable=False, index=True)
    numero = Column(Integer, nullable=False)                          # consecutivo dentro de la asamblea
    titulo = Column(String(160), nullable=False)
    descripcion = Column(String(500), nullable=True)
    tipo = Column(String(10), nullable=False)                         # Decisión | Elección
    mayoria = Column(String(12), nullable=False, default="Simple")    # Simple | Calificada
    estado = Column(String(10), nullable=False, default="Borrador")   # Borrador | Abierta | Cerrada | Anulada
    creada_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)
    # --- al abrir ---
    abierta_en = Column(DateTime, nullable=True)
    abierta_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    padron = Column(Text, nullable=True)                              # JSON: unidades que pueden votar, con su coeficiente y por qué vía (App | Manual)
    coef_padron = Column(Float, nullable=True)                        # suma del coeficiente del padrón (la base de la mayoría simple)
    coef_total = Column(Float, nullable=True)                         # el 100 % del conjunto en ese momento (la base de la mayoría calificada)
    quorum_apertura = Column(Float, nullable=True)                    # % del coeficiente presente al abrir
    # --- al cerrar o anular ---
    cerrada_en = Column(DateTime, nullable=True)
    cerrada_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    quorum_cierre = Column(Float, nullable=True)
    resultado = Column(Text, nullable=True)                           # JSON congelado del resultado
    resultado_hash = Column(String(64), nullable=True)                # SHA-256 de ese JSON (también queda en la bitácora)
    motivo_anulacion = Column(String(200), nullable=True)


class AsambleaVotacionOpcion(Base):
    """Una opción de la pregunta y cuánto lleva. El voto de la app es SECRETO: este contador no está unido a ninguna persona."""
    __tablename__ = "asamblea_votacion_opciones"

    id = Column(Integer, primary_key=True, index=True)
    votacion_id = Column(Integer, ForeignKey("asamblea_votaciones.id"), nullable=False, index=True)
    texto = Column(String(120), nullable=False)
    orden = Column(Integer, nullable=False, default=0)
    conteo = Column(Integer, nullable=False, default=0)               # unidades que la escogieron
    peso = Column(Float, nullable=False, default=0.0)                 # suma de sus coeficientes (%)


class AsambleaVoto(Base):
    """Que una unidad YA votó (la restricción única impide votar dos veces, aunque lleguen dos peticiones a la vez).
    Voto por la app (asistente virtual): `opcion_id` queda VACÍO, así nadie puede saber qué votó (voto secreto).
    Voto registrado por el administrador (asistente presencial): `opcion_id` guarda lo que se votó (voto nominal, queda a nombre de la unidad)."""
    __tablename__ = "asamblea_votos"
    __table_args__ = (UniqueConstraint("votacion_id", "unidad_id", name="uq_asamblea_voto_unidad"),)

    id = Column(Integer, primary_key=True, index=True)
    votacion_id = Column(Integer, ForeignKey("asamblea_votaciones.id"), nullable=False, index=True)
    unidad_id = Column(Integer, ForeignKey("unidades.id"), nullable=False)
    asistente_id = Column(Integer, ForeignKey("asamblea_asistentes.id"), nullable=False)
    peso = Column(Float, nullable=False)                              # coeficiente (%) con el que votó la unidad (el del padrón)
    via = Column(String(6), nullable=False)                           # App | Manual
    emitido_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    opcion_id = Column(Integer, ForeignKey("asamblea_votacion_opciones.id"), nullable=True)   # solo en votos Manual
    fecha = Column(DateTime, default=ahora_utc)
