# app/routers/usuarios.py
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import sesiones
from app.auditoria import auditar
from app.constantes import RolNombre
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import Rol, Usuario
from app.schemas.usuarios import ParqueaderoUpdate, PasswordTemporalResponse, UsuarioCreateAdmin, UsuarioResponse
from app.security import encriptar_password

router = APIRouter(prefix="/usuarios", tags=["Usuarios (Administración)"])

solo_admin = requiere_roles(RolNombre.ADMINISTRADOR)


@router.get("/me", response_model=UsuarioResponse, summary="Ver mi perfil",
            description="Devuelve los datos del usuario dueño del token. Cualquier rol.")
def mi_perfil(usuario: Usuario = Depends(get_current_user)):
    return usuario


@router.get("/", response_model=list[UsuarioResponse], summary="Listar todos los usuarios",
            description="Solo **Administrador**.")
def listar_usuarios(db: Session = Depends(get_db), _: Usuario = Depends(solo_admin)):
    return db.query(Usuario).order_by(Usuario.id).all()


@router.post("/", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED,
             summary="Crear un usuario con cualquier rol",
             description="Solo **Administrador**. Sirve para crear celadores (Guardia) u otros administradores.",
             responses={400: {"description": "El correo ya está registrado"}})
def crear_usuario(datos: UsuarioCreateAdmin, db: Session = Depends(get_db), admin: Usuario = Depends(solo_admin)):
    if db.query(Usuario).filter(Usuario.email == datos.email).first():
        raise HTTPException(status_code=400, detail="El correo electrónico ya se encuentra registrado.")
    rol = db.query(Rol).filter(Rol.nombre == datos.rol.value).first()
    if rol is None:
        raise HTTPException(status_code=500, detail="Roles sin configurar. Ejecuta: alembic upgrade head")

    nuevo = Usuario(
        nombre_completo=datos.nombre_completo,
        email=datos.email,
        password_encriptada=encriptar_password(datos.password),
        rol_id=rol.id,
        apartamento=datos.apartamento,
    )
    db.add(nuevo)
    db.flush()
    auditar(db, admin, "Creó usuario", "Usuario", nuevo.id, f"{nuevo.nombre_completo} ({datos.rol.value})")
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.patch("/{usuario_id}/parqueadero", response_model=UsuarioResponse, summary="Asignar parqueadero",
              description="Solo **Administrador**.", responses={404: {"description": "Usuario no encontrado"}})
def asignar_parqueadero(usuario_id: int, datos: ParqueaderoUpdate, db: Session = Depends(get_db),
                        admin: Usuario = Depends(solo_admin)):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    auditar(db, admin, "Asignó parqueadero", "Usuario", usuario.id, f"{usuario.nombre_completo}: {datos.parqueadero_asignado}")
    usuario.parqueadero_asignado = datos.parqueadero_asignado
    db.commit()
    db.refresh(usuario)
    return usuario


@router.patch("/{usuario_id}/activo", response_model=UsuarioResponse, summary="Activar o desactivar un usuario",
              description="Solo **Administrador**. Un usuario desactivado no puede iniciar sesión y su token deja de funcionar. "
              "Un administrador no puede desactivarse a sí mismo.",
              responses={404: {"description": "Usuario no encontrado"}, 400: {"description": "Acción no permitida"}})
def cambiar_activo(usuario_id: int, esta_activo: bool, db: Session = Depends(get_db),
                   admin: Usuario = Depends(solo_admin)):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if usuario.id == admin.id and not esta_activo:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta.")
    usuario.esta_activo = esta_activo
    if not esta_activo:
        sesiones.revocar_todas(db, usuario.id)
    auditar(db, admin, "Activó usuario" if esta_activo else "Desactivó usuario", "Usuario", usuario.id, usuario.nombre_completo)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.post("/{usuario_id}/restablecer-password", response_model=PasswordTemporalResponse,
             summary="Restablecer la contraseña de un usuario",
             description="Solo **Administrador**. Genera una contraseña temporal que se muestra **una sola vez**; la persona deberá "
                         "cambiarla al ingresar. Úsalo cuando alguien olvide su clave. No se puede usar sobre tu propia cuenta "
                         "(para eso está `POST /auth/cambiar-password`).",
             responses={404: {"description": "Usuario no encontrado"}, 400: {"description": "Es tu propia cuenta"}})
def restablecer_password(usuario_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(solo_admin)):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if usuario.id == admin.id:
        raise HTTPException(status_code=400, detail="Para cambiar tu propia contraseña usa «Cambiar contraseña» en Configuración.")
    temporal = secrets.token_urlsafe(9)   # 12 caracteres al azar
    usuario.password_encriptada = encriptar_password(temporal)
    usuario.debe_cambiar_password = True
    sesiones.revocar_todas(db, usuario.id)       # la clave anterior ya no vale, tampoco las sesiones abiertas con ella
    auditar(db, admin, "Restableció contraseña", "Seguridad", usuario.id, usuario.nombre_completo)
    db.commit()
    return {"password_temporal": temporal, "mensaje": f"Entrégale esta clave a {usuario.nombre_completo}. Deberá cambiarla al ingresar."}
