# app/models.py
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
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
    rol_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    rol_rel = relationship("Rol", back_populates="usuarios", lazy="joined")

    apartamento = Column(String, nullable=True)
    esta_activo = Column(Boolean, default=True)

    # CANDADO FINANCIERO: True = al día / False = en mora
    esta_al_dia = Column(Boolean, default=True)
    valor_administracion = Column(Integer, default=150000)
    saldo_pendiente = Column(Integer, default=0)
    parqueadero_asignado = Column(String, default="Ninguno")

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
    fecha_ingreso = Column(DateTime, default=ahora_utc)
    fecha_salida = Column(DateTime, nullable=True)
    estado = Column(String, default="Dentro")  # Dentro | Salido
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
    cerrada_en = Column(DateTime, nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)


class VotacionOpcion(Base):
    __tablename__ = "votacion_opciones"

    id = Column(Integer, primary_key=True)
    votacion_id = Column(Integer, ForeignKey("votaciones.id"), nullable=False, index=True)
    texto = Column(String, nullable=False)
    orden = Column(Integer, nullable=False, default=0)
    conteo = Column(Integer, nullable=False, default=0)


class VotacionParticipacion(Base):
    """Quién ya votó (no qué votó). La restricción única impide votar dos veces aunque lleguen dos peticiones a la vez."""
    __tablename__ = "votacion_participaciones"
    __table_args__ = (UniqueConstraint("votacion_id", "clave", name="uq_participacion_votacion_clave"),)

    id = Column(Integer, primary_key=True)
    votacion_id = Column(Integer, ForeignKey("votaciones.id"), nullable=False, index=True)
    clave = Column(String, nullable=False)                    # «apto:torre 1 apt 101» o «usr:15»
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
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
    motivo_cierre = Column(String, nullable=True)
    aprobado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion = Column(DateTime, default=ahora_utc)
    fecha_decision = Column(DateTime, nullable=True)

    propietario = relationship("Usuario", foreign_keys=[propietario_id])
    inquilino = relationship("Usuario", foreign_keys=[inquilino_id])
