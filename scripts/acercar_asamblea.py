# scripts/acercar_asamblea.py — SOLO PARA PRUEBAS EN TU COMPUTADOR.
# Una asamblea convocada tiene su reunión dentro de varios días y no se puede instalar antes de la hora (es una regla legal). Para probar el recorrido completo
# (acreditar, instalar, votar, cerrar) sin esperar, este script mueve la hora de la reunión a «ahora».
# SE NIEGA a funcionar si la base de datos no es SQLite (la de tu computador): así es imposible que toque Supabase o producción.
# Uso (con el entorno virtual activo y desde la carpeta del proyecto):   python -m scripts.acercar_asamblea 1        (1 = número de la asamblea)
import sys
from datetime import timedelta

from app.config import DATABASE_URL
from app.database import SessionLocal
from app.models import Asamblea, ahora_utc


def main() -> int:
    if not DATABASE_URL.startswith("sqlite"):
        print("NO se hizo nada: este script solo funciona con la base SQLite de tu computador (tu DATABASE_URL apunta a otra base).")
        return 1
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print("Uso: python -m scripts.acercar_asamblea <número de la asamblea>")
        return 2
    with SessionLocal() as db:
        a = db.query(Asamblea).filter(Asamblea.id == int(sys.argv[1])).one_or_none()
        if a is None:
            print("Esa asamblea no existe.")
            return 3
        if a.estado != "Convocada":
            print(f"La asamblea está «{a.estado}»: solo se acerca una asamblea «Convocada».")
            return 4
        a.fecha_sesion = ahora_utc()
        a.fecha_segunda = a.fecha_sesion + timedelta(hours=72)
        db.commit()
        print(f"Listo: la asamblea «{a.titulo}» quedó citada para ahora. Ya puedes acreditar asistentes e instalarla.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
