# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

# 'check_same_thread' solo aplica a SQLite. Con PostgreSQL (Supabase) no se envía.
_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# pool_pre_ping evita errores por conexiones caídas (útil con Supabase).
engine = create_engine(DATABASE_URL, connect_args=_args, pool_pre_ping=True)

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
