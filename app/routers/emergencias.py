# app/routers/emergencias.py
# Bloque 2 · Contactos de emergencia: directorio del conjunto (policía, bomberos, clínica, gas, administración...).
# Todos lo consultan; solo el administrador lo edita. Las líneas nacionales vienen cargadas por la migración 0006.
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auditoria import auditar
from app.constantes import RolNombre
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import ContactoEmergencia, Usuario
from app.schemas.negocio import MensajeResponse
from app.schemas.operacion import ContactoCreate, ContactoResponse, ContactoUpdate

TAG = "Contactos de Emergencia"
router = APIRouter(prefix="/emergencias", tags=[TAG])
ADMIN = RolNombre.ADMINISTRADOR
MAX_CONTACTOS = 60


def _obtener(db: Session, contacto_id: int) -> ContactoEmergencia:
    c = db.get(ContactoEmergencia, contacto_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Contacto no encontrado.")
    return c


@router.get("/", response_model=list[ContactoResponse], summary="Ver el directorio de emergencias",
            description="Roles: **todos**. Ordenado por `orden` y luego por nombre.")
def listar(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return db.query(ContactoEmergencia).order_by(ContactoEmergencia.orden, ContactoEmergencia.nombre).all()


@router.post("/", response_model=ContactoResponse, status_code=status.HTTP_201_CREATED, summary="Agregar un contacto de emergencia",
             description="Rol: **Administrador**. Máximo 60 contactos.", responses={400: {"description": "Límite de contactos alcanzado"}})
def crear(datos: ContactoCreate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    if db.query(func.count(ContactoEmergencia.id)).scalar() >= MAX_CONTACTOS:
        raise HTTPException(status_code=400, detail=f"Ya hay {MAX_CONTACTOS} contactos. Elimina alguno para agregar otro.")
    c = ContactoEmergencia(nombre=datos.nombre, telefono=datos.telefono, categoria=datos.categoria.value,
                           descripcion=datos.descripcion, orden=datos.orden)
    db.add(c)
    db.flush()
    auditar(db, admin, "Agregó contacto de emergencia", "Emergencia", c.id, f"{c.nombre}: {c.telefono}")
    db.commit()
    db.refresh(c)
    return c


@router.patch("/{contacto_id}", response_model=ContactoResponse, summary="Editar un contacto de emergencia",
              description="Rol: **Administrador**. Solo se cambia lo que se envíe.", responses={404: {"description": "Contacto no encontrado"}})
def editar(contacto_id: int, datos: ContactoUpdate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    c = _obtener(db, contacto_id)
    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        if campo in ("nombre", "telefono", "categoria", "orden") and valor is None:
            continue   # estos campos no admiten vacío
        if campo == "categoria":
            valor = valor.value
        if campo == "nombre":
            valor = " ".join(valor.split())
        if campo == "descripcion":
            valor = " ".join((valor or "").split()) or None
        setattr(c, campo, valor)
    auditar(db, admin, "Editó contacto de emergencia", "Emergencia", c.id, f"{c.nombre}: {c.telefono} (campos: {', '.join(cambios)})")
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{contacto_id}", response_model=MensajeResponse, summary="Eliminar un contacto de emergencia",
               description="Rol: **Administrador**.", responses={404: {"description": "Contacto no encontrado"}})
def eliminar(contacto_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    c = _obtener(db, contacto_id)
    auditar(db, admin, "Eliminó contacto de emergencia", "Emergencia", c.id, f"{c.nombre}: {c.telefono}")
    db.delete(c)
    db.commit()
    return {"mensaje": "Contacto eliminado."}
