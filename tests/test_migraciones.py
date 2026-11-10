# tests/test_migraciones.py
# Simula tu base de datos ANTIGUA (con la columna de texto "rol" y datos reales)
# y comprueba que la migración con Alembic no pierde nada.
import hashlib
import os
import sqlite3
import tempfile

from alembic import command
from alembic.config import Config

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _config(url: str) -> Config:
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _crear_bd_antigua(ruta: str) -> None:
    """Las tablas tal como las creaba el proyecto antes de agregar roles."""
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE usuarios (id INTEGER PRIMARY KEY, nombre_completo VARCHAR NOT NULL, email VARCHAR NOT NULL,
            password_encriptada VARCHAR NOT NULL, rol VARCHAR, apartamento VARCHAR, esta_activo BOOLEAN,
            esta_al_dia BOOLEAN, valor_administracion INTEGER, saldo_pendiente INTEGER, parqueadero_asignado VARCHAR);
        CREATE UNIQUE INDEX ix_usuarios_email ON usuarios (email);
        CREATE TABLE reservas (id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
            zona_comun VARCHAR NOT NULL, fecha_reserva DATETIME NOT NULL, estado VARCHAR, fecha_creacion DATETIME);
        CREATE TABLE reportes_danios (id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
            titulo VARCHAR NOT NULL, descripcion VARCHAR NOT NULL, foto_url VARCHAR, estado VARCHAR, fecha_creacion DATETIME);
        CREATE TABLE vehiculos_visitantes (id INTEGER PRIMARY KEY, placa VARCHAR NOT NULL,
            apartamento_destino VARCHAR NOT NULL, fecha_ingreso DATETIME, fecha_salida DATETIME, estado VARCHAR);
    """)
    sha = hashlib.sha256(b"clave123").hexdigest()
    con.executemany(
        "INSERT INTO usuarios (id, nombre_completo, email, password_encriptada, rol, apartamento, esta_activo, esta_al_dia,"
        " valor_administracion, saldo_pendiente, parqueadero_asignado) VALUES (?,?,?,?,?,?,1,0,150000,50000,'P-1')",
        [(1, "Admin Viejo", "admin@x.com", sha, "Administrador", None),
         (2, "Resi Vieja", "resi@x.com", sha, "Residente", "T1 101"),
         (3, "Celador Viejo", "cel@x.com", sha, "Celador", None),
         (4, "Rol Raro", "raro@x.com", sha, "Inventado", None)])
    con.execute("INSERT INTO reservas (usuario_id, zona_comun, fecha_reserva, estado) VALUES (2, 'Zona BBQ', '2026-12-01 10:00:00', 'Pendiente')")
    con.commit()
    con.close()


def test_migracion_conserva_datos_y_convierte_roles():
    ruta = os.path.join(tempfile.mkdtemp(), "antigua.db")
    _crear_bd_antigua(ruta)
    cfg = _config(f"sqlite:///{ruta}")

    command.upgrade(cfg, "head")

    con = sqlite3.connect(ruta)
    filas = con.execute("SELECT u.id, u.email, r.nombre, u.saldo_pendiente, u.parqueadero_asignado "
                        "FROM usuarios u JOIN roles r ON r.id = u.rol_id ORDER BY u.id").fetchall()
    assert filas == [(1, "admin@x.com", "Administrador", 50000, "P-1"),
                     (2, "resi@x.com", "Residente", 50000, "P-1"),
                     (3, "cel@x.com", "Guardia", 50000, "P-1"),     # Celador -> Guardia
                     (4, "raro@x.com", "Residente", 50000, "P-1")]  # rol desconocido -> el de menos permisos
    assert "rol" not in [c[1] for c in con.execute("PRAGMA table_info(usuarios)")]   # columna de texto eliminada
    assert con.execute("SELECT count(*) FROM reservas").fetchone()[0] == 1           # otras tablas intactas
    cols = [c[1] for c in con.execute("PRAGMA table_info(vehiculos_visitantes)")]
    assert {"ingreso_registrado_por", "salida_registrada_por"} <= set(cols)           # trazabilidad de portería
    con.close()

    command.downgrade(cfg, "0001")  # y se puede devolver sin perder el rol
    con = sqlite3.connect(ruta)
    assert con.execute("SELECT rol FROM usuarios WHERE id = 3").fetchone()[0] == "Guardia"
    con.close()


def test_migracion_en_base_vacia_crea_todo():
    ruta = os.path.join(tempfile.mkdtemp(), "nueva.db")
    command.upgrade(_config(f"sqlite:///{ruta}"), "head")
    con = sqlite3.connect(ruta)
    tablas = {t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"usuarios", "roles", "reservas", "reportes_danios", "vehiculos_visitantes", "anuncios", "anuncio_asistencias", "codigos_qr", "escaneos_qr", "publicidad", "auditoria", "intentos_login",
            "visitantes_autorizados", "accesos_visitantes", "paquetes", "contactos_emergencia", "notificaciones", "pqrs", "documentos", "pagos", "alembic_version"} <= tablas
    assert con.execute("SELECT count(*) FROM roles").fetchone()[0] == 3
    assert [t[0] for t in con.execute("SELECT telefono FROM contactos_emergencia ORDER BY orden")] == ["123", "112", "119", "132", "144"]
    con.close()
