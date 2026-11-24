# scripts/medir_rendimiento.py
# Mide cuántas consultas SQL y cuántos milisegundos gasta cada pantalla (endpoint GET) con un conjunto «grande» de datos.
# Sirve para encontrar el problema N+1 (una consulta por cada fila) y para comparar ANTES y DESPUÉS de optimizar.
# Usa una base SQLite temporal: NO toca tu base real.   Uso:   python -m scripts.medir_rendimiento
import logging
import os
import random
import tempfile
import time
from datetime import timedelta

_TMP = tempfile.mkdtemp(prefix="medicion_")
os.environ.update(SECRET_KEY="clave-solo-para-medir-0123456789abcdef01234567", DATABASE_URL=f"sqlite:///{_TMP}/m.db",
                  UPLOAD_DIR=f"{_TMP}/up", BCRYPT_ROUNDS="4", ALMACEN="local", VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
                  IA_API_KEY="", GEMINI_API_KEY="", SMTP_HOST="")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (AccesoVisitante, Anuncio, Auditoria, CodigoQR, EscaneoQR, Notificacion, Paquete, PQRS, Reserva, Rol,  # noqa: E402
                        Usuario, VehiculoVisitante, VisitanteAutorizado, ahora_utc)
from app.security import encriptar_password  # noqa: E402
from app.seed import asegurar_roles  # noqa: E402

logging.disable(logging.CRITICAL)      # sin el ruido de «INFO» de cada petición: solo queremos la tabla final

CLAVE = "claveSegura123"
N_RESIDENTES = 200


def sembrar() -> None:
    Base.metadata.create_all(bind=engine)
    random.seed(7)
    with SessionLocal() as db:
        asegurar_roles(db)
        rol = {r.nombre: r.id for r in db.query(Rol).all()}
        h = encriptar_password(CLAVE)
        db.add_all([Usuario(nombre_completo="Admin", email="admin@m.com", password_encriptada=h, rol_id=rol["Administrador"]),
                    Usuario(nombre_completo="Guardia", email="guardia@m.com", password_encriptada=h, rol_id=rol["Guardia"])])
        db.add_all([Usuario(nombre_completo=f"Residente {i}", email=f"r{i}@m.com", password_encriptada=h, rol_id=rol["Residente"],
                            apartamento=f"Torre {i % 8 + 1} Apt {100 + i}", saldo_pendiente=random.choice([0, 0, 150000, 300000]),
                            esta_al_dia=random.random() > 0.2) for i in range(1, N_RESIDENTES + 1)])
        db.commit()
        ids = [u.id for u in db.query(Usuario).filter(Usuario.email.like("r%@m.com")).all()]
        ahora = ahora_utc()
        db.add_all([Reserva(usuario_id=random.choice(ids), zona_comun=random.choice(["Zona BBQ", "Salón social", "Piscina"]),
                            fecha_reserva=ahora + timedelta(days=random.randint(-700, 60)), estado=random.choices(["Pendiente", "Aprobada", "Cancelada"], [2, 88, 10])[0])   # ~2 años de historial, pocas pendientes (como en la vida real)
                    for _ in range(3000)])
        db.add_all([VehiculoVisitante(placa=f"ABC{random.randint(100, 999)}", apartamento_destino="Torre 1 Apt 101",
                                      fecha_ingreso=ahora - timedelta(hours=random.randint(1, 3000)), estado="Salido") for _ in range(4000)])
        db.add_all([Paquete(destinatario_id=random.choice(ids), remitente="Servientrega",
                            estado=random.choice(["En porteria", "Entregado"]), recibido_por=2) for _ in range(3000)])
        db.add_all([PQRS(usuario_id=random.choice(ids), tipo="Queja", asunto="Ruido", descripcion="x" * 80) for _ in range(800)])
        db.add_all([Anuncio(autor_id=1, titulo=f"Aviso {i}", contenido="x" * 200) for i in range(120)])
        db.add_all([Notificacion(usuario_id=random.choice(ids), titulo="Aviso", mensaje="x") for _ in range(4000)])
        db.add_all([Auditoria(actor_id=1, accion="Algo", entidad="Reserva") for _ in range(5000)])
        db.commit()
        codigos = []
        for i in range(600):
            c = CodigoQR(usuario_id=random.choice(ids), tipo="Visitante", token=f"tok{i}_{random.random()}", nombre_visitante="Visita", placa="ABC123")
            db.add(c)
            codigos.append(c)
        db.commit()
        db.add_all([EscaneoQR(codigo_id=random.choice(codigos).id, escaneado_por=2, resultado="Ingreso registrado") for _ in range(3000)])
        db.commit()
        # Fase 5: datos que alimentan los indicadores (si no existen, la medición del dashboard sale artificialmente barata)
        db.add_all([PQRS(usuario_id=random.choice(ids), tipo="Queja", asunto="Respondida", descripcion="x" * 80, estado="Resuelta",
                         fecha_creacion=ahora - timedelta(days=random.randint(3, 80)), fecha_respuesta=ahora - timedelta(days=random.randint(0, 2)))
                    for _ in range(2000)])
        db.add(VisitanteAutorizado(usuario_id=ids[0], nombre="Visita frecuente", documento="1"))
        db.commit()
        vid = db.query(VisitanteAutorizado).first().id
        for _ in range(20000):      # entradas a pie de los últimos 30 días; todas con su salida (en la vida real casi nadie está «dentro» a la vez)
            entro = ahora - timedelta(minutes=random.randint(120, 30 * 24 * 60))
            db.add(AccesoVisitante(visitante_id=vid, fecha_ingreso=entro, fecha_salida=entro + timedelta(hours=1)))
        db.commit()


class Contador:
    def __init__(self):
        self.n = 0
        event.listen(engine, "before_cursor_execute", self._cuenta)

    def _cuenta(self, *_):
        self.n += 1


def entrar(cliente: TestClient, email: str) -> dict:
    r = cliente.post("/auth/login", data={"username": email, "password": CLAVE})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _dia(delta=0):
    return (ahora_utc() + timedelta(days=delta)).strftime("%Y-%m-%d")


RUTAS = {
    "admin": ["/dashboard/kpis?refrescar=true", "/administracion/cartera", "/reservas/listar?estado=Pendiente", f"/reservas/listar?desde={_dia(-90)}","/usuarios/", "/reservas/listar", "/reservas/ocupacion?zona=Zona%20BBQ&mes=2026-11", "/mantenimiento/listar-danios", "/anuncios/", "/paquetes/",
              "/paquetes/destinatarios", "/pqrs/", "/auditoria/", "/qr/visitantes?todos=true", "/qr/escaneos", "/comercio/gestion",
              "/porteria/historial", "/porteria/vehiculos-dentro", "/notificaciones/", "/notificaciones/conteo", "/votaciones/",
              "/documentos/", "/arrendamientos/", "/visitantes-autorizados/accesos", "/usuarios/me", "/emergencias/"],
    "guardia": [f"/reservas/listar?estado=Aprobada&desde={_dia()}&hasta={_dia()}", "/qr/escaneos", "/paquetes/", "/paquetes/destinatarios", "/porteria/historial", "/visitantes-autorizados/dentro",
                "/visitantes-autorizados/accesos", "/reservas/listar"],
    "residente": ["/reservas/mis-reservas", "/anuncios/", "/paquetes/", "/pqrs/", "/qr/visitantes", "/notificaciones/",
                  "/notificaciones/conteo", "/usuarios/me", "/administracion/mis-pagos", "/votaciones/"],
}
CORREOS = {"admin": "admin@m.com", "guardia": "guardia@m.com", "residente": "r5@m.com"}


def medir() -> list[tuple]:
    cliente = TestClient(app)
    cont = Contador()
    filas = []
    for rol, rutas in RUTAS.items():
        cab = entrar(cliente, CORREOS[rol])
        for ruta in rutas:
            cliente.get(ruta, headers=cab)                      # calentamiento (importaciones, caché de SQLAlchemy)
            tiempos, consultas = [], 0
            for _ in range(3):
                cont.n = 0
                t = time.perf_counter()
                r = cliente.get(ruta, headers=cab)
                tiempos.append((time.perf_counter() - t) * 1000)
                consultas = cont.n
            filas.append((rol, ruta, r.status_code, consultas, min(tiempos), len(r.content)))
    return filas


if __name__ == "__main__":
    sembrar()
    print(f"Datos: {N_RESIDENTES} residentes · 3000 reservas · 4000 vehículos · 3000 paquetes · 4000 notificaciones · 5000 auditorías · 2000 PQRS respondidas · 20000 accesos a pie\n")
    print(f"{'rol':9} {'ruta':36} {'HTTP':>4} {'SQL':>5} {'ms':>8} {'KB':>7}")
    for rol, ruta, st, n, ms, tam in sorted(medir(), key=lambda f: -f[3]):
        marca = "  <-- N+1?" if n > 15 else ""
        print(f"{rol:9} {ruta:36} {st:>4} {n:>5} {ms:>8.1f} {tam / 1024:>7.1f}{marca}")
