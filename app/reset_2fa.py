# app/reset_2fa.py
# Rescate: quita la verificación en dos pasos de una cuenta (por ejemplo, si el único administrador perdió el celular Y los códigos de recuperación).
# Se corre en el servidor (en Render: pestaña «Shell»; en tu computador: con el .env cargado), así que solo puede hacerlo quien controla el servidor:
#     python -m app.reset_2fa correo@del.administrador
# Cierra todas las sesiones de esa cuenta y deja una línea en la auditoría.
import sys

from app import sesiones
from app.auditoria import auditar
from app.database import SessionLocal
from app.models import Usuario


def main(correo: str) -> int:
    with SessionLocal() as db:
        u = db.query(Usuario).filter(Usuario.email == correo.strip()).first()
        if u is None:
            print(f"No existe ninguna cuenta con el correo {correo!r}.")
            return 1
        u.totp_activo, u.totp_secreto, u.totp_ultimo_paso, u.codigos_recuperacion = False, None, None, None
        cerradas = sesiones.revocar_todas(db, u.id)
        auditar(db, None, "Quitó la verificación en dos pasos (rescate por el servidor)", "Seguridad", u.id, f"cerró {cerradas} sesión(es)")
        db.commit()
        print(f"Listo: {u.email} ya no tiene verificación en dos pasos y se cerraron {cerradas} sesión(es). Que la vuelva a activar al entrar.")
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python -m app.reset_2fa correo@del.administrador")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
