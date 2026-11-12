# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

# 'check_same_thread' solo aplica a SQLite. Con PostgreSQL (Supabase) no se envía.
_es_sqlite = DATABASE_URL.startswith("sqlite")
_args = {"check_same_thread": False} if _es_sqlite else {}
# Con PostgreSQL (Supabase) se reutilizan conexiones abiertas en vez de abrir una nueva por petición (abrir una cuesta ~100-300 ms por la red).
# pool_recycle renueva las conexiones antes de que el «pooler» de Supabase las cierre por inactividad.
_pool = {} if _es_sqlite else {"pool_size": 5, "max_overflow": 5, "pool_recycle": 280, "pool_timeout": 20}

# pool_pre_ping evita errores por conexiones caídas (útil con Supabase).
engine = create_engine(DATABASE_URL, connect_args=_args, pool_pre_ping=True, **_pool)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Todos los modelos (tablas) heredan de esta clase.
Base = declarative_base()


def get_db():
    """Dependencia: entrega una sesión por petición y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
