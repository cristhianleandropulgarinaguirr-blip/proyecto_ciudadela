# app/demo_reservas.py — Versión 3.2: reservas de EJEMPLO para demostrar el chat (opcional y reversible).
# Uso (desde la carpeta del proyecto, con el entorno virtual activo):
#     python -m app.demo_reservas --crear      crea ~90 días de reservas de ejemplo (pide confirmación)
#     python -m app.demo_reservas --borrar     las elimina por completo (y también al usuario de ejemplo)
# Todas pertenecen a un usuario inactivo «Datos de ejemplo» (no puede iniciar sesión ni recibe avisos), así que
# se identifican y se borran sin tocar ninguna reserva real. Los patrones son inventados: úsalo solo para mostrar el chat.
import argparse
import random
import secrets
from datetime import datetime, timedelta

from app.chat_datos import ZONAS
from app.constantes import EstadoReserva, RolNombre
from app.database import SessionLocal
from app.models import Reserva, Rol, Usuario
from app.security import encriptar_password

EMAIL_DEMO = "datos.de.ejemplo@ciudadela.invalid"
# Peso por día de la semana (lun..dom): cuanto más alto, más probable que ese día haya reserva.
PESOS = {
    "Zona BBQ": [.05, .05, .08, .12, .45, .85, .70],
    "Piscina": [.10, .08, .10, .15, .40, .80, .75],
    "Salón Comunal": [.04, .04, .06, .10, .50, .70, .30],
    "Gimnasio": [.30, .30, .30, .25, .15, .10, .05],
    "Cancha múltiple": [.10, .10, .35, .15, .20, .65, .40],
    "Sala de juegos": [.08, .08, .08, .12, .25, .40, .50],
}
HORAS = {"Zona BBQ": (12, 14, 18), "Piscina": (10, 11, 15), "Salón Comunal": (14, 18, 19), "Gimnasio": (6, 7, 18, 19),
         "Cancha múltiple": (8, 16, 17), "Sala de juegos": (15, 16, 17)}


def crear(db, dias_atras: int = 90, dias_adelante: int = 14, semilla: int = 7) -> int:
    if db.query(Usuario).filter(Usuario.email == EMAIL_DEMO).first():
        raise ValueError("Ya hay datos de ejemplo. Bórralos primero con --borrar si quieres volver a generarlos.")
    rol = db.query(Rol).filter(Rol.nombre == RolNombre.RESIDENTE.value).one()
    demo = Usuario(nombre_completo="Datos de ejemplo", email=EMAIL_DEMO, password_encriptada=encriptar_password(secrets.token_urlsafe(24)),
                   rol_id=rol.id, apartamento=None, esta_activo=False)
    db.add(demo)
    db.flush()
    azar, hoy, total = random.Random(semilla), datetime.now().replace(minute=0, second=0, microsecond=0), 0
    for d in range(-dias_atras, dias_adelante + 1):
        dia = hoy + timedelta(days=d)
        if d == 0:
            continue
        for zona in ZONAS:                                           # máximo una reserva por zona y día, como exige la app
            if azar.random() < PESOS[zona][dia.weekday()]:
                estado = EstadoReserva.APROBADA.value if (d < 0 or azar.random() < .8) else EstadoReserva.PENDIENTE.value
                db.add(Reserva(usuario_id=demo.id, zona_comun=zona, fecha_reserva=dia.replace(hour=azar.choice(HORAS[zona])), estado=estado))
                total += 1
    db.commit()
    return total


def borrar(db) -> int:
    demo = db.query(Usuario).filter(Usuario.email == EMAIL_DEMO).first()
    if not demo:
        return 0
    n = db.query(Reserva).filter(Reserva.usuario_id == demo.id).delete()
    db.delete(demo)
    db.commit()
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Reservas de ejemplo para demostrar el chat.")
    grupo = ap.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--crear", action="store_true", help="crea las reservas de ejemplo")
    grupo.add_argument("--borrar", action="store_true", help="elimina las reservas de ejemplo y su usuario")
    args = ap.parse_args()
    with SessionLocal() as db:
        if args.borrar:
            print(f"Se eliminaron {borrar(db)} reservas de ejemplo.")
            return
        if input("Esto agrega reservas de EJEMPLO a la base de datos configurada en .env. ¿Continuar? (escribe SI): ").strip().upper() != "SI":
            print("Cancelado.")
            return
        try:
            print(f"Listo: {crear(db)} reservas de ejemplo creadas. Para quitarlas: python -m app.demo_reservas --borrar")
        except ValueError as e:
            print(e)


if __name__ == "__main__":
    main()
