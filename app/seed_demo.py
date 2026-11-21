# app/seed_demo.py — Versión 4.0 (Fase 4 · presentación comercial): un conjunto de EJEMPLO completo para mostrar la app a un cliente.
#
# Uso (desde la carpeta del proyecto, con el entorno virtual activo y el .env apuntando a la base de DEMOSTRACIÓN):
#     python -m app.seed_demo --crear                 crea el conjunto de ejemplo (pide confirmación) y muestra las cuentas para entrar
#     python -m app.seed_demo --borrar                lo elimina por completo, sin tocar nada real
#     python -m app.seed_demo --reiniciar             borra y vuelve a crear (deja la demo como nueva antes de cada presentación)
#     python -m app.seed_demo --crear --clave Demo2026   usa esa clave para las cuentas de ejemplo (si no, se genera una al azar)
#
# Qué crea (todo inventado; los nombres y teléfonos no son de personas reales):
#   · 30 apartamentos en 2 torres (5 pisos × 3 por torre) con propietarios, coeficientes de copropiedad que suman EXACTAMENTE 100 % y cuota proporcional.
#   · 6 apartamentos en mora y 24 al día, con su historial de pagos; 3 paz y salvos vigentes.
#   · 4 inquilinos con contrato activo (y 1 contrato pendiente de aprobación), 2 guardias.
#   · Reservas de los últimos 60 días y los próximos 14, paquetes, PQRS con respuesta, daños, cartelera, una votación abierta por coeficiente y una cerrada,
#     visitantes y vehículos, trasteos, directorio de emergencias, negocios de vecinos y bitácora de auditoría.
#
# Cómo se mantiene seguro:
#   · NO crea ningún administrador con clave conocida: usas el administrador que ya tienes (el de `python -m app.seed`).
#     Lo que hace «de administración» (anuncios, respuestas…) lo firma un usuario INACTIVO «Administración del conjunto (demo)» que no puede iniciar sesión.
#   · Todas las cuentas de ejemplo terminan en @demo.example.com (un dominio reservado que no existe): así se reconocen y se borran sin tocar nada real.
#   · Se niega a correr si la base ya tiene residentes reales (a menos que uses --forzar): mezclar propietarios reales con los de ejemplo dañaría los coeficientes.
import argparse
import random
import re
import secrets
import unicodedata
from datetime import datetime, timedelta

import sqlalchemy as sa

from app import config
from app.arrendamientos import ahora_local
from app.chat_datos import ZONAS
from app.constantes import EstadoReserva, RolNombre
from app.database import Base, SessionLocal, engine
from app.demo_reservas import HORAS, PESOS
from app.models import (
    AccesoVisitante, Anuncio, AnuncioAsistencia, Arrendamiento, Auditoria, ContactoEmergencia, IntentoLogin, Pago, PazSalvo, Paquete, PQRS, Publicidad, ReporteDanio, Reserva, Rol,
    Trasteo, Usuario, VehiculoVisitante, VisitanteAutorizado, Votacion, VotacionOpcion, VotacionParticipacion, ahora_utc,
)
from app.security import encriptar_password
from app.seed import asegurar_roles

DOMINIO = "demo.example.com"
EMAIL_ADMINISTRACION = f"administracion@{DOMINIO}"
EMAIL_ADMIN_DEMO = f"administrador@{DOMINIO}"          # v5.0 · el administrador de la demo LOCAL (solo se crea con --local o con_admin=True, en una base exclusiva de la demo)
PRESUPUESTO_MENSUAL = 7_900_000          # lo que el conjunto necesita recaudar al mes; la cuota de cada apartamento sale de su coeficiente
ORDEN_EMERGENCIAS = 9000                 # los contactos de emergencia de ejemplo llevan un `orden` reservado (9000+) para poder borrarlos sin tocar los reales

# 30 propietarios de ejemplo (nombre, apellidos). Inventados.
PROPIETARIOS = [
    ("Marcela", "Rojas Pardo"), ("Andrés", "Duarte Salcedo"), ("Paola", "Barrera Niño"), ("Julián", "Castañeda Lozano"), ("Natalia", "Moreno Cifuentes"),
    ("Sebastián", "Ortiz Vargas"), ("Luisa", "Quintero Bernal"), ("Diego", "Beltrán Acosta"), ("Daniela", "Gaitán Ruiz"), ("Mauricio", "Pineda Camacho"),
    ("Carolina", "Suárez Villamil"), ("Esteban", "Cárdenas Peña"), ("Viviana", "Murillo Torres"), ("Jhon Jairo", "Forero Rincón"), ("Liliana", "Arévalo Mesa"),
    ("Santiago", "Becerra Díaz"), ("Yesenia", "Cortés Montoya"), ("Óscar", "Lemus Prieto"), ("Laura", "Tovar Gómez"), ("Hernán", "Salamanca Roa"),
    ("Stefanía", "Niño Hurtado"), ("Cristian", "Parra Zambrano"), ("Mónica", "Valencia Ríos"), ("Wilson", "Garzón Bautista"), ("Tatiana", "Cuervo Medina"),
    ("Alejandro", "Sierra Cano"), ("Gloria", "Bohórquez Silva"), ("Fabián", "Mejía Ramírez"), ("Adriana", "Lugo Herrera"), ("Rodrigo", "Pacheco Triana"),
]
INQUILINOS = [("Valentina", "Osorio Prada"), ("Camilo", "Espinosa León"), ("Karen", "Rueda Marín"), ("Iván", "Zapata Cruz"), ("Lorena", "Aponte Giraldo")]
GUARDIAS = [("Wilmer", "Ospina Duarte"), ("Rosalba", "Mendoza Ariza")]
AREAS_M2 = {1: 58.4, 2: 71.9, 3: 84.6}                  # tres tipos de apartamento por piso
INDICES_EN_MORA = (3, 8, 12, 17, 21, 26)                  # posiciones (0-29) de los apartamentos en mora
INDICES_CON_INQUILINO = (2, 7, 14, 20)                    # contrato activo
INDICE_CONTRATO_PENDIENTE = 10
LETRAS_PLACA = "ABCDEFGHJKLMNPRSTUVWXYZ"


def _plano(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", ".", unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()).strip(".")


def _correo(nombre: str, apellidos: str, usados: set) -> str:
    base = f"{_plano(nombre.split()[0])}.{_plano(apellidos.split()[0])}"
    correo, n = f"{base}@{DOMINIO}", 2
    while correo in usados:
        correo, n = f"{base}{n}@{DOMINIO}", n + 1
    usados.add(correo)
    return correo


def _celular(n: int) -> str:
    return f"310000{n:04d}"           # 310 000 00NN: claramente de ejemplo


def _placa(azar: random.Random) -> str:
    return "".join(azar.choice(LETRAS_PLACA) for _ in range(3)) + "".join(str(azar.randint(0, 9)) for _ in range(3))


def _apartamentos() -> list[str]:
    return [f"Torre {t} Apt {p * 100 + u}" for t in (1, 2) for p in range(1, 6) for u in (1, 2, 3)]


def _coeficientes() -> list[float]:
    """Coeficiente de copropiedad = área del apartamento / área total. Redondeado a 4 decimales y ajustado para que sumen EXACTAMENTE 100."""
    areas = [AREAS_M2[u] + (6.0 if p == 5 else 0.0) for _ in (1, 2) for p in range(1, 6) for u in (1, 2, 3)]
    total = sum(areas)
    coefs = [round(a / total * 100, 4) for a in areas]
    coefs[-1] = round(100 - sum(coefs[:-1]), 4)
    return coefs


def _rol_id(db, nombre: RolNombre) -> int:
    return db.query(Rol).filter(Rol.nombre == nombre.value).one().id


# ---------------------------------------------------------------------------------------------- crear
def hay_datos_de_ejemplo(db) -> bool:
    return db.query(Usuario.id).filter(Usuario.email.like(f"%@{DOMINIO}")).first() is not None


def crear(db, clave: str, semilla: int = 2026, forzar: bool = False, con_admin: bool = False) -> dict:
    """Crea el conjunto de ejemplo y devuelve lo necesario para entrar (cuentas) y un resumen de cantidades."""
    asegurar_roles(db)
    if hay_datos_de_ejemplo(db):
        raise ValueError("Ya hay datos de ejemplo. Bórralos con --borrar (o usa --reiniciar) si quieres volver a generarlos.")
    reales = (db.query(Usuario.id).join(Rol, Rol.id == Usuario.rol_id)
              .filter(Rol.nombre == RolNombre.RESIDENTE.value, Usuario.esta_activo.is_(True)).count())
    if reales and not forzar:
        raise ValueError(f"Esta base ya tiene {reales} residentes reales. Mezclarlos con el conjunto de ejemplo dañaría los coeficientes y los indicadores. "
                         "Usa una base solo para demostraciones (o --forzar si estás seguro).")
    if con_admin and not forzar:      # v5.0: un administrador con clave conocida SOLO puede existir en una base que es exclusivamente de la demo
        reales_activos = db.query(Usuario.id).filter(Usuario.esta_activo.is_(True), ~Usuario.email.like(f"%@{DOMINIO}")).count()
        if reales_activos:
            raise ValueError(f"Esta base tiene {reales_activos} usuario(s) reales activos. El administrador de demostración (con clave conocida) solo se crea en una base "
                             "exclusiva de la demo, nunca junto a datos reales.")
    azar = random.Random(semilla)
    ahora, local = ahora_utc(), ahora_local()
    clave_hash = encriptar_password(clave)            # un solo cálculo (es lento a propósito) para todas las cuentas
    usados: set = set()
    rid = {r: _rol_id(db, r) for r in RolNombre}
    resumen: dict = {}

    def dia_a_las(dias: int, hora: int, minuto: int = 0) -> datetime:
        """Fecha UTC de «dentro de N días a las H:MM» en hora de Colombia (UTC-5)."""
        return ahora.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=dias, hours=hora + 5, minutes=minuto)

    def nuevo_usuario(nombre, apellidos, rol, **campos) -> Usuario:
        u = Usuario(nombre_completo=f"{nombre} {apellidos}", email=_correo(nombre, apellidos, usados), password_encriptada=clave_hash, rol_id=rid[rol],
                    politica_datos_fecha=ahora - timedelta(days=60), **campos)
        db.add(u)
        return u

    # --- quién firma lo «de administración»: un usuario inactivo (no puede entrar ni recibe avisos)
    admin = Usuario(nombre_completo="Administración del conjunto (demo)", email=EMAIL_ADMINISTRACION, password_encriptada=encriptar_password(secrets.token_urlsafe(24)),
                    rol_id=rid[RolNombre.ADMINISTRADOR], esta_activo=False)
    db.add(admin)
    admin_demo = None
    if con_admin:      # v5.0 · el administrador con el que se PRESENTA la demo (misma clave de todas las cuentas de ejemplo)
        admin_demo = Usuario(nombre_completo="Administrador (demo)", email=EMAIL_ADMIN_DEMO, password_encriptada=clave_hash, rol_id=rid[RolNombre.ADMINISTRADOR],
                             politica_datos_fecha=ahora - timedelta(days=60))
        db.add(admin_demo)

    # --- 30 propietarios
    aptos, coefs = _apartamentos(), _coeficientes()
    propietarios: list[Usuario] = []
    parqueaderos = iter(f"P-{n:02d}" for n in range(1, 23))
    for i, ((nombre, apellidos), apto, coef) in enumerate(zip(PROPIETARIOS, aptos, coefs)):
        cuota = int(round(coef / 100 * PRESUPUESTO_MENSUAL, -3))
        en_mora = i in INDICES_EN_MORA
        meses = azar.choice((1, 2, 2, 3))
        propietarios.append(nuevo_usuario(nombre, apellidos, RolNombre.RESIDENTE, apartamento=apto, coeficiente=coef, valor_administracion=cuota,
                                          saldo_pendiente=cuota * meses if en_mora else 0, esta_al_dia=not en_mora,
                                          parqueadero_asignado=next(parqueaderos, "Ninguno")))
    # --- inquilinos (4 activos + 1 pendiente), guardias
    inquilinos = []
    for (nombre, apellidos), i in zip(INQUILINOS, (*INDICES_CON_INQUILINO, INDICE_CONTRATO_PENDIENTE)):
        pendiente = i == INDICE_CONTRATO_PENDIENTE
        inquilinos.append((nuevo_usuario(nombre, apellidos, RolNombre.INQUILINO, apartamento=aptos[i], esta_activo=not pendiente, debe_cambiar_password=pendiente), i, pendiente))
    guardias = [nuevo_usuario(n, a, RolNombre.GUARDIA) for n, a in GUARDIAS]
    db.flush()
    resumen["apartamentos"], resumen["usuarios"] = len(propietarios), 1 + len(propietarios) + len(inquilinos) + len(guardias)
    al_dia = [u for u in propietarios if u.esta_al_dia]
    en_mora = [u for u in propietarios if not u.esta_al_dia]
    guardia = guardias[0]

    # --- contratos de arrendamiento
    for k, (inq, i, pendiente) in enumerate(inquilinos):
        db.add(Arrendamiento(propietario_id=propietarios[i].id, inquilino_id=inq.id, apartamento=aptos[i], fecha_inicio=local - timedelta(days=150 if not pendiente else 0),
                             fecha_fin=local + timedelta(days=210 if not pendiente else 365), estado="Pendiente" if pendiente else "Activo",
                             puede_pagar=k in (0, 2), puede_votar=k in (0, 1), aprobado_por=None if pendiente else admin.id,
                             fecha_decision=None if pendiente else ahora - timedelta(days=150)))

    # --- pagos de los últimos 3 meses de quienes están al día
    pagos = 0
    for u in al_dia:
        for mes in range(azar.choice((1, 2, 3)), 0, -1):
            db.add(Pago(usuario_id=u.id, valor=u.valor_administracion, saldo_anterior=u.valor_administracion, saldo_posterior=0,
                        fecha=ahora - timedelta(days=30 * mes - azar.randint(0, 9), hours=azar.randint(0, 8))))
            pagos += 1
    resumen["pagos"] = pagos

    # --- paz y salvo (3) + trasteos
    paz = []
    for u, destino in zip(al_dia[:3], ("Banco de crédito de vivienda", "Inmobiliaria", "Empresa de trasteos")):
        p = PazSalvo(usuario_id=u.id, codigo=secrets.token_urlsafe(16), destino=destino, fecha_emision=ahora - timedelta(days=5), valido_hasta=ahora + timedelta(days=25), emitido_por=admin.id)
        db.add(p)
        paz.append(p)
    db.flush()
    sal, llega = al_dia[2], al_dia[5]
    db.add_all([
        Trasteo(solicitante_id=sal.id, titular_id=sal.id, apartamento=sal.apartamento, tipo="Salida", fecha_inicio=dia_a_las(3, 8),
                fecha_fin=dia_a_las(3, 14), empresa="Trasteos Camino Seguro", placa=_placa(azar), estado="Aprobado", paz_salvo_id=paz[2].id,
                decidido_por=admin.id, fecha_decision=ahora - timedelta(days=1)),
        Trasteo(solicitante_id=llega.id, titular_id=llega.id, apartamento=llega.apartamento, tipo="Entrada", fecha_inicio=dia_a_las(8, 9),
                fecha_fin=dia_a_las(8, 13), empresa="Mudanzas La Sabana", placa=_placa(azar), estado="Pendiente"),
        Trasteo(solicitante_id=al_dia[7].id, titular_id=al_dia[7].id, apartamento=al_dia[7].apartamento, tipo="Entrada", fecha_inicio=ahora - timedelta(days=20, hours=4),
                fecha_fin=ahora - timedelta(days=20), empresa="Fletes Rápidos", placa=_placa(azar), estado="Completado", decidido_por=admin.id,
                fecha_decision=ahora - timedelta(days=22), registrado_por=guardia.id, inicio_real=ahora - timedelta(days=20, hours=4), fin_real=ahora - timedelta(days=20, hours=1)),
    ])

    # --- reservas: 60 días atrás y 14 adelante; solo quienes están al día reservan hacia adelante (la mora bloquea reservar, como en la app)
    reservas = 0
    for d in range(-60, 15):
        dia = local.replace(minute=0, second=0, microsecond=0) + timedelta(days=d)
        if d == 0:
            continue
        for zona in ZONAS:                                    # máximo una reserva por zona y día
            if azar.random() >= PESOS[zona][dia.weekday()]:
                continue
            quien = azar.choice(propietarios if d < 0 else al_dia)
            estado = EstadoReserva.APROBADA.value
            if d > 0 and azar.random() < .25:
                estado = EstadoReserva.PENDIENTE.value
            elif d < 0 and azar.random() < .06:
                estado = EstadoReserva.CANCELADA.value
            db.add(Reserva(usuario_id=quien.id, zona_comun=zona, fecha_reserva=dia.replace(hour=azar.choice(HORAS[zona])), estado=estado,
                           fecha_creacion=ahora + timedelta(days=min(d, 0) - azar.randint(1, 6))))
            reservas += 1
    resumen["reservas"] = reservas

    # --- paquetes (6 en portería y 6 entregados)
    remitentes = ["Mercado Libre", "Amazon", "Servientrega", "Coordinadora", "Rappi", "Inter Rapidísimo", "Falabella.com", "Envía", "Linio", "Domicilios Pizzería"]
    for k in range(12):
        dest = azar.choice(propietarios)
        entregado = k >= 6
        recibido = ahora - timedelta(days=azar.randint(0, 2) if not entregado else azar.randint(3, 25), hours=azar.randint(0, 9))
        db.add(Paquete(destinatario_id=dest.id, tipo=azar.choice(("Paquete", "Paquete", "Correspondencia", "Domicilio")), remitente=azar.choice(remitentes),
                       descripcion=azar.choice(("Caja mediana", "Sobre", "Bolsa", "Caja pequeña", "Caja grande")), estado="Entregado" if entregado else "En porteria",
                       recibido_por=guardia.id, fecha_recepcion=recibido, entregado_a=dest.nombre_completo if entregado else None,
                       entregado_por=guardia.id if entregado else None, fecha_entrega=recibido + timedelta(hours=azar.randint(1, 20)) if entregado else None))

    # --- PQRS (algunas respondidas: el indicador de tiempo de respuesta sale con datos)
    pqrs = [
        ("Queja", "Ruido en el piso de arriba después de las 11 p. m.", "Desde hace dos semanas se escucha música alta entre semana. Pedimos que la administración hable con los vecinos.", "Resuelta",
         "Hablamos con el apartamento y se acordó respetar el horario de silencio. Avísanos si se repite."),
        ("Peticion", "Más bicicleteros en el sótano", "Los bicicleteros actuales están llenos. ¿Se podría instalar otro módulo cerca de la rampa?", "En tramite", "Estamos cotizando el módulo adicional."),
        ("Reclamo", "Cobro de intereses en mi cuota", "Pagué el día 4 por transferencia y me cobraron intereses de mora. Adjunto el soporte en portería.", "Resuelta",
         "Revisamos el soporte: el pago estaba dentro del plazo. Ajustamos el saldo y quedó al día."),
        ("Sugerencia", "Horario extendido de la piscina los sábados", "Muchas familias trabajan hasta tarde. Sugiero abrir hasta las 8 p. m. los sábados.", "Radicada", None),
        ("Queja", "Basuras en el cuarto de reciclaje", "Dejan bolsas sin separar y huele mal. Falta señalización.", "Resuelta", "Pusimos carteles y reforzamos el aseo del cuarto dos veces por semana."),
        ("Peticion", "Constancia de residencia", "Necesito una constancia de que vivo en el conjunto para un trámite bancario.", "Resuelta", "Listo: puedes descargar tu paz y salvo desde la sección correspondiente."),
        ("Sugerencia", "Más iluminación en el parque infantil", "Al anochecer el parque queda muy oscuro. Sería bueno agregar dos luminarias.", "En tramite", "Se incluyó en el presupuesto de mantenimiento."),
        ("Reclamo", "Ascensor de la Torre 2 detenido", "Esta semana el ascensor se quedó parado dos veces con personas adentro.", "Resuelta", "La empresa de mantenimiento cambió la tarjeta de control el martes."),
        ("Queja", "Mascotas sin correa en zonas comunes", "Varios perros andan sueltos junto a los niños.", "Radicada", None),
        ("Peticion", "Autorización para obra menor en cocina", "Quiero cambiar el mesón. ¿Qué requisitos pide el reglamento?", "Cerrada", "Te enviamos por correo el formato de autorización de obras."),
    ]
    for k, (tipo, asunto, desc, estado, resp) in enumerate(pqrs):
        creada = ahora - timedelta(days=azar.randint(2, 55), hours=azar.randint(0, 12))
        respondida = creada + timedelta(hours=azar.randint(3, 40)) if resp else None
        db.add(PQRS(usuario_id=propietarios[(k * 3 + 1) % 30].id, tipo=tipo, asunto=asunto, descripcion=desc, estado=estado, respuesta=resp,
                    respondido_por=admin.id if resp else None, fecha_respuesta=respondida, fecha_creacion=creada, fecha_actualizacion=respondida or creada))

    # --- reportes de daños
    danios = [
        ("Bombillo dañado en el pasillo del piso 3", "El bombillo frente al apartamento lleva una semana apagado.", "Solucionado"),
        ("Fuga en el sótano", "Hay una gotera constante junto al parqueadero P-07.", "En Reparacion"),
        ("Portón peatonal no cierra", "El portón peatonal de la Torre 1 queda entreabierto.", "En Revision"),
        ("Grieta en la cancha múltiple", "Se abrió una grieta cerca del arco norte.", "Abierto"),
        ("Citófono sin audio", "El citófono del Apt 305 no deja escuchar a portería.", "Solucionado"),
        ("Reja del jardín suelta", "Se soltó un tramo de reja junto a la zona BBQ.", "Abierto"),
        ("Humedad en el techo del salón comunal", "Aparecieron manchas después de la lluvia.", "En Revision"),
        ("Timbre de la entrada vehicular", "No suena cuando llega un domiciliario.", "Solucionado"),
    ]
    for k, (titulo, desc, estado) in enumerate(danios):
        db.add(ReporteDanio(usuario_id=propietarios[(k * 4 + 2) % 30].id, titulo=titulo, descripcion=desc, estado=estado, fecha_creacion=ahora - timedelta(days=azar.randint(1, 45))))

    # --- cartelera
    anuncios = [
        Anuncio(autor_id=admin.id, titulo="Asamblea ordinaria de copropietarios", tipo="Reunion", fijado=True, lugar="Salón Comunal", fecha_evento=dia_a_las(12, 19),
                contenido="Se presentarán el informe de gestión y el presupuesto del próximo año. Recuerda estar al día para votar. Si no puedes asistir, puedes delegar el voto."),
        Anuncio(autor_id=admin.id, titulo="Suspensión del agua el jueves", tipo="Urgente", fecha_evento=dia_a_las(4, 9), lugar="Todo el conjunto",
                contenido="Por mantenimiento de la red del acueducto, el agua se suspenderá entre las 9:00 a. m. y las 3:00 p. m. Almacena lo que necesites."),
        Anuncio(autor_id=admin.id, titulo="Novena de aguinaldos", tipo="Evento", fecha_evento=dia_a_las(30, 18, 30), lugar="Parque central",
                contenido="Invitamos a todas las familias a la primera novena. Habrá chocolate y buñuelos. Trae tu taza."),
        Anuncio(autor_id=admin.id, titulo="Lavado de tanques de agua", tipo="Mantenimiento", fecha_evento=dia_a_las(9, 8), lugar="Torres 1 y 2",
                contenido="Se hará el lavado y desinfección de los tanques. Durante la jornada la presión puede bajar."),
        Anuncio(autor_id=admin.id, titulo="Nuevo horario del gimnasio", tipo="Aviso",
                contenido="Desde este mes el gimnasio abre de 5:00 a. m. a 10:00 p. m. Recuerda reservar tu turno para las clases en grupo."),
    ]
    for k, a in enumerate(anuncios):
        a.fecha_creacion = ahora - timedelta(days=k * 2, hours=k)
    db.add_all(anuncios)
    db.flush()
    for u in azar.sample(propietarios, 11):
        db.add(AnuncioAsistencia(anuncio_id=anuncios[0].id, usuario_id=u.id))
    for u in azar.sample(propietarios, 6):
        db.add(AnuncioAsistencia(anuncio_id=anuncios[2].id, usuario_id=u.id))

    # --- votaciones: una abierta (por coeficiente, exige estar al día) y una cerrada
    abierta = Votacion(autor_id=admin.id, titulo="Cámaras y cerca eléctrica para la portería", estado="Abierta", fecha_inicio=ahora - timedelta(days=2), fecha_cierre=ahora + timedelta(days=6),
                       descripcion="¿Aprueba invertir en cámaras nuevas y cerca eléctrica en el perímetro? Cada voto pesa según el coeficiente del apartamento.",
                       un_voto_por="apartamento", ponderada=True, exige_al_dia=True, resultados_en_vivo=False)
    cerrada = Votacion(autor_id=admin.id, titulo="Horario de la piscina en vacaciones", estado="Cerrada", fecha_inicio=ahora - timedelta(days=24), fecha_cierre=ahora - timedelta(days=10),
                       cerrada_en=ahora - timedelta(days=10), descripcion="¿Hasta qué hora debe funcionar la piscina en temporada de vacaciones?", un_voto_por="apartamento",
                       ponderada=False, exige_al_dia=False, resultados_en_vivo=True)
    db.add_all([abierta, cerrada])
    db.flush()
    opc_a = [VotacionOpcion(votacion_id=abierta.id, texto=t, orden=o) for o, t in enumerate(("Aprobar cámaras y cerca", "Aprobar solo las cámaras", "No aprobar"))]
    opc_c = [VotacionOpcion(votacion_id=cerrada.id, texto=t, orden=o) for o, t in enumerate(("Hasta las 6 p. m.", "Hasta las 8 p. m.", "Sin cambios"))]
    db.add_all(opc_a + opc_c)
    db.flush()
    for u in azar.sample(al_dia, 13):                       # votación abierta: solo votan quienes están al día
        o = azar.choices(opc_a, weights=(5, 3, 2))[0]
        o.conteo, o.peso = o.conteo + 1, round(o.peso + u.coeficiente, 4)
        db.add(VotacionParticipacion(votacion_id=abierta.id, clave=f"apto:{u.apartamento.casefold()}", usuario_id=u.id, peso=u.coeficiente, fecha=ahora - timedelta(hours=azar.randint(1, 40))))
    for u in azar.sample(propietarios, 19):
        o = azar.choices(opc_c, weights=(3, 5, 2))[0]
        o.conteo += 1
        db.add(VotacionParticipacion(votacion_id=cerrada.id, clave=f"apto:{u.apartamento.casefold()}", usuario_id=u.id, fecha=ahora - timedelta(days=azar.randint(11, 23))))

    # --- visitantes autorizados y sus accesos, vehículos de visitantes
    tipos = [("Familiar", "Mamá de la propietaria"), ("Servicio domestico", "Aseo los martes y viernes"), ("Contratista", "Plomero de confianza"), ("Amigo", "Compañero de estudio"),
             ("Cuidador", "Cuidadora de adulto mayor"), ("Familiar", "Hermano")]
    visitantes = []
    for k, (tipo, nota) in enumerate(tipos):
        v = VisitanteAutorizado(usuario_id=propietarios[(k * 5 + 4) % 30].id, nombre=azar.choice(("Rosa Elena", "Pedro Nel", "Marta Lucía", "Juan Camilo", "Sandra Milena", "Luis Carlos")) + " " + azar.choice(("Peña", "Roa", "Soto", "Vega", "Ibáñez", "Mora")),
                                documento=f"100000{k:04d}", tipo=tipo, notas=nota, vigente_hasta=ahora + timedelta(days=90) if k % 2 else None)
        db.add(v)
        visitantes.append(v)
    db.flush()
    for v in visitantes[:5]:
        for _ in range(azar.randint(2, 4)):
            entra = ahora - timedelta(days=azar.randint(1, 20), hours=azar.randint(0, 6))
            db.add(AccesoVisitante(visitante_id=v.id, fecha_ingreso=entra, fecha_salida=entra + timedelta(hours=azar.randint(1, 5)), ingreso_registrado_por=guardia.id, salida_registrada_por=guardia.id))
    for k in range(18):
        dentro = k < 2
        entra = ahora - timedelta(hours=azar.randint(1, 3)) if dentro else ahora - timedelta(days=azar.randint(1, 28), hours=azar.choice((14, 15, 16, 17, 20, 22, 23, 1)))
        db.add(VehiculoVisitante(placa=_placa(azar), apartamento_destino=azar.choice(aptos), fecha_ingreso=entra, fecha_salida=None if dentro else entra + timedelta(hours=azar.randint(1, 5)),
                                 estado="Dentro" if dentro else "Salido", ingreso_registrado_por=guardia.id, salida_registrada_por=None if dentro else guardia.id))

    # --- comercio entre vecinos
    negocios = [
        ("Sazón de la Abuela", "Comida", "Almuerzos caseros a domicilio en el conjunto", "Corrientazo desde $14.000 · lunes a sábado", "Cocina tradicional, porciones generosas y entrega en tu puerta."),
        ("Patitas Felices", "Mascotas", "Paseo y baño de mascotas", "Paseo desde $12.000", "Paseos diarios en las zonas verdes y baño con secado. Cupos limitados."),
        ("Refuerzo con Profe Daniela", "Educacion", "Clases de matemáticas y lectura", "Hora desde $25.000", "Refuerzo escolar para primaria, presencial o virtual."),
        ("Electrodomésticos Hernán", "Servicios", "Reparación de lavadoras y neveras", "Revisión desde $30.000", "Servicio técnico con garantía. Vecino del conjunto."),
    ]
    for k, (nombre, cat, titulo, precio, desc) in enumerate(negocios):
        db.add(Publicidad(propietario_id=propietarios[(k * 6 + 3) % 30].id, nombre_negocio=nombre, categoria=cat, titulo=titulo, descripcion=desc, precio_texto=precio,
                          whatsapp=_celular(50 + k), plan="Mensual", valor=45000, estado="Activa", fecha_inicio=ahora - timedelta(days=8 + k), fecha_fin=ahora + timedelta(days=22 - k),
                          contactos=azar.randint(3, 19), revisado_por=admin.id))
    db.add(Publicidad(propietario_id=propietarios[16].id, nombre_negocio="Repostería Dulce Hogar", categoria="Comida", titulo="Tortas y postres por encargo", descripcion="Tortas personalizadas para cumpleaños.",
                      precio_texto="Tortas desde $60.000", whatsapp=_celular(54), plan="Semanal", valor=15000, estado="En revision", referencia_pago="TRF-DEMO-0001"))

    # --- emergencias (números nacionales reales) y contactos del conjunto
    contactos = [("Línea única de emergencias", "123", "Emergencias", "Policía, ambulancia y bomberos"), ("Bomberos", "119", "Emergencias", None), ("Cruz Roja Colombiana", "132", "Salud", None),
                 ("Defensa Civil", "144", "Emergencias", None), ("GAULA (secuestro y extorsión)", "165", "Seguridad", None),
                 ("Portería del conjunto", "(601) 000 0101", "Administracion", "24 horas"), ("Oficina de administración", "(601) 000 0100", "Administracion", "Lunes a viernes, 8 a. m. a 5 p. m.")]
    for k, (nombre, tel, cat, desc) in enumerate(contactos):
        db.add(ContactoEmergencia(nombre=nombre, telefono=tel, categoria=cat, descripcion=desc, orden=ORDEN_EMERGENCIAS + k))

    # --- auditoría (para que la pantalla no esté vacía)
    acciones = [("Registró pago", "Cartera", "Pago de cuota de administración"), ("Aprobó reserva", "Reserva", "Salón Comunal"), ("Respondió PQRS", "PQRS", "Respuesta enviada al residente"),
                ("Publicó anuncio", "Anuncio", "Cartelera"), ("Aprobó arrendamiento", "Arrendamiento", "Contrato de 12 meses"), ("Emitió paz y salvo", "Usuario", "Vigencia de 30 días")]
    for k in range(12):
        a = acciones[k % len(acciones)]
        db.add(Auditoria(actor_id=admin.id, accion=a[0], entidad=a[1], detalle=f"{a[2]} · {azar.choice(aptos)}", fecha=ahora - timedelta(days=k * 2, hours=azar.randint(0, 9))))

    db.commit()
    resumen.update({"en_mora": len(en_mora), "al_dia": len(al_dia), "inquilinos": len(inquilinos), "guardias": len(guardias), "coeficiente_total": round(sum(coefs), 4)})
    return {"resumen": resumen, "clave": clave, "cuentas": [
        ("Administrador", EMAIL_ADMIN_DEMO, "administrador de la demo") if admin_demo else ("Administrador", "el que ya tienes (el de python -m app.seed)", "tu clave de siempre"),
        ("Residente al día", al_dia[0].email, f"{al_dia[0].apartamento}"),
        ("Residente en mora", en_mora[0].email, f"{en_mora[0].apartamento} · debe ${en_mora[0].saldo_pendiente:,}".replace(",", ".")),
        ("Inquilino", inquilinos[0][0].email, f"{inquilinos[0][0].apartamento} · puede pagar y votar"),
        ("Guardia", guardia.email, "portería"),
    ]}


# ---------------------------------------------------------------------------------------------- borrar
def borrar(db) -> int:
    """Elimina TODO lo de ejemplo: los usuarios @demo.example.com y cada fila que dependa de ellos (reservas, pagos, votaciones, accesos…),
    más los vehículos que registró el guardia de ejemplo y los contactos de emergencia reservados. No toca datos reales:
    lo que tenga una referencia opcional a un usuario de ejemplo (p. ej. un paquete real recibido por un guardia de ejemplo) solo pierde esa referencia."""
    ids_usuarios = {i for (i,) in db.query(Usuario.id).filter(Usuario.email.like(f"%@{DOMINIO}")).all()}
    if not ids_usuarios:
        return 0
    meta = Base.metadata
    pendientes: dict[str, set] = {"usuarios": set(ids_usuarios)}
    # Filas que se borran aunque su referencia al usuario sea opcional (son datos de ejemplo por sí mismas).
    pendientes["vehiculos_visitantes"] = {i for (i,) in db.query(VehiculoVisitante.id).filter(VehiculoVisitante.ingreso_registrado_por.in_(ids_usuarios)).all()}
    pendientes["auditoria"] = {i for (i,) in db.query(Auditoria.id).filter(Auditoria.actor_id.in_(ids_usuarios)).all()}
    pendientes["contactos_emergencia"] = {i for (i,) in db.query(ContactoEmergencia.id).filter(ContactoEmergencia.orden >= ORDEN_EMERGENCIAS).all()}
    anuladas: list = []                                      # (tabla, columna, ids) → poner NULL
    cambio = True
    while cambio:                                            # cascada: lo que depende de lo que se borra, también se borra
        cambio = False
        for tabla in meta.sorted_tables:
            pk = list(tabla.primary_key.columns)
            if len(pk) != 1:
                continue
            for fk in tabla.foreign_keys:
                padre = fk.column.table.name
                if padre not in pendientes or not pendientes[padre]:
                    continue
                col = fk.parent
                ids_padre = pendientes[padre]
                filas = {i for (i,) in db.execute(sa.select(pk[0]).where(col.in_(ids_padre))).all()}
                if not filas:
                    continue
                if col.nullable and tabla.name not in ("usuarios",):
                    if (tabla.name, col.name) not in {(a[0].name, a[1].name) for a in anuladas}:
                        anuladas.append((tabla, col, filas))
                    continue
                nuevos = filas - pendientes.setdefault(tabla.name, set())
                if nuevos:
                    pendientes[tabla.name] |= nuevos
                    cambio = True
    for tabla, col, _ in anuladas:                           # primero se sueltan las referencias opcionales hacia lo que se va a borrar…
        padre = next(fk.column.table.name for fk in col.foreign_keys)
        db.execute(sa.update(tabla).where(col.in_(pendientes[padre])).values({col.name: None}))
    total = 0
    for tabla in reversed(meta.sorted_tables):               # …y luego se borra de lo más dependiente a lo menos
        ids = pendientes.get(tabla.name)
        if ids:
            pk = list(tabla.primary_key.columns)[0]
            total += db.execute(sa.delete(tabla).where(pk.in_(ids))).rowcount or 0
    total += db.query(IntentoLogin).filter(IntentoLogin.clave.like(f"%@{DOMINIO}")).delete(synchronize_session=False)    # contadores de fallos de login de esas cuentas
    db.commit()
    return total


# ---------------------------------------------------------------------------------------------- línea de comandos
def _imprimir_cuentas(r: dict) -> None:
    res = r["resumen"]
    print(f"\nListo. Se creó el conjunto de ejemplo: {res['apartamentos']} apartamentos ({res['al_dia']} al día, {res['en_mora']} en mora), "
          f"{res['inquilinos']} inquilinos, {res['guardias']} guardias, {res['reservas']} reservas y {res['pagos']} pagos. Coeficientes: suman {res['coeficiente_total']} %.")
    print(f"\nCLAVE de todas las cuentas de ejemplo: {r['clave']}\n")
    ancho = max(len(c[1]) for c in r["cuentas"])
    for rol, correo, nota in r["cuentas"]:
        print(f"  {rol:<18} {correo:<{ancho}}  {nota}")
    print("\nPara quitar todo: python -m app.seed_demo --borrar")


CLAVE_DEMO_LOCAL = "Demo2026"      # clave de las cuentas de la demo LOCAL (es una base de mentira, exclusiva de la demo; puedes cambiarla con --clave)


def preparar_local(db, clave: str) -> dict | None:
    """v5.0 · Deja lista la demo de tu computador. Si la base ya tiene el conjunto de ejemplo no toca nada (devuelve None); si está vacía lo crea
    CON un administrador de demostración (administrador@demo.example.com). Es idempotente: iniciar-demo.bat la llama en cada arranque."""
    asegurar_roles(db)
    if hay_datos_de_ejemplo(db):
        return None
    return crear(db, clave, con_admin=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Conjunto de ejemplo (30 apartamentos) para presentar la app a un cliente.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--crear", action="store_true", help="crea el conjunto de ejemplo")
    g.add_argument("--borrar", action="store_true", help="elimina por completo el conjunto de ejemplo")
    g.add_argument("--reiniciar", action="store_true", help="borra y vuelve a crear (demo como nueva)")
    g.add_argument("--local", action="store_true", help="prepara la demo en tu computador (solo con MODO_DEMO=1): si su base está vacía crea el conjunto de ejemplo CON un "
                                                       "administrador de demostración; si ya existe no toca nada. Lo usa iniciar-demo.bat; no pide confirmación")
    ap.add_argument("--clave", help="clave de las cuentas de ejemplo (si no, se genera una al azar). Mínimo 8 caracteres.")
    ap.add_argument("--con-admin", action="store_true", help="además crea el administrador de demostración (administrador@demo.example.com) con esa misma clave; solo en una base exclusiva de la demo")
    ap.add_argument("--forzar", action="store_true", help="permite crear aunque la base ya tenga residentes reales (no recomendado)")
    ap.add_argument("--si", action="store_true", help="no pedir confirmación (para scripts)")
    args = ap.parse_args()
    if args.clave and len(args.clave) < 8:
        ap.error("la clave debe tener al menos 8 caracteres")
    if args.local and not config.MODO_DEMO:
        ap.error("--local solo corre con MODO_DEMO=1 (así nunca toca la base de tu app real). Usa iniciar-demo.bat, que ya lo activa.")
    with SessionLocal() as db:
        if args.local:
            try:
                r = preparar_local(db, args.clave or CLAVE_DEMO_LOCAL)
            except ValueError as e:
                return print(e)
            if r is None:
                return print(f"La demo local ya estaba lista ({engine.url.render_as_string(hide_password=True)}). Administrador: {EMAIL_ADMIN_DEMO}. "
                             "Si quieres dejarla como nueva: python -m app.seed_demo --reiniciar --con-admin --si")
            return _imprimir_cuentas(r)
        if args.borrar or args.reiniciar:
            if not args.si and input(f"Esto ELIMINA los datos de ejemplo (@{DOMINIO}) de la base configurada en .env: {engine.url.render_as_string(hide_password=True)}\n¿Continuar? (escribe SI): ").strip().upper() != "SI":
                return print("Cancelado.")
            print(f"Se eliminaron {borrar(db)} filas de ejemplo.")
            if args.borrar:
                return
        elif not args.si and input(f"Esto AGREGA un conjunto de EJEMPLO a la base configurada en .env: {engine.url.render_as_string(hide_password=True)}\n¿Continuar? (escribe SI): ").strip().upper() != "SI":
            return print("Cancelado.")
        try:
            _imprimir_cuentas(crear(db, args.clave or f"Demo-{secrets.token_urlsafe(6)}", forzar=args.forzar, con_admin=args.con_admin))
        except ValueError as e:
            print(e)


if __name__ == "__main__":
    main()
