# app/routers/importaciones.py
# Carga masiva por Excel/CSV (solo administrador): el censo de apartamentos y la cartera mensual.
# Flujo en dos pasos para que nadie dañe datos por accidente:
#   1) POST /importaciones/{tipo}/vista-previa → valida TODO el archivo y dice qué se crearía/actualizaría y qué filas tienen errores. No guarda nada.
#   2) POST /importaciones/{tipo}/aplicar      → vuelve a validar y guarda todo en UNA transacción (o todo o nada).
# El servidor no guarda el archivo entre los dos pasos (así no queda ningún dato personal «en espera»): el navegador lo vuelve a enviar.
import io
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import coeficientes, importacion as imp
from app.auditoria import auditar
from app.constantes import RolNombre
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import Rol, Usuario
from app.schemas.importaciones import CredencialNueva, FilaImportacion, ResumenImportacion
from app.security import encriptar_password

TAG = "Carga masiva (Excel/CSV)"
router = APIRouter(prefix="/importaciones", tags=[TAG])
ADMIN = RolNombre.ADMINISTRADOR
Tipo = Literal["residentes", "cartera"]
MAX_FILAS_LISTADAS = 400          # filas válidas que se devuelven en la vista previa (los errores se devuelven todos)
LOTE_IN = 400                     # SQLite admite máx. 999 parámetros en un IN: se consulta por lotes


def _leer_subida(archivo: UploadFile) -> bytes:
    datos = archivo.file.read(imp.MAX_BYTES + 1)           # nunca se carga más de lo permitido en memoria
    if len(datos) > imp.MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"El archivo pesa más de {imp.MAX_BYTES // 1024 // 1024} MB.")
    return datos


def _por_correos(db: Session, correos: list[str]) -> dict[str, Usuario]:
    encontrados: dict[str, Usuario] = {}
    for i in range(0, len(correos), LOTE_IN):
        for u in db.query(Usuario).filter(func.lower(Usuario.email).in_(correos[i:i + LOTE_IN])).all():
            encontrados[u.email.lower()] = u
    return encontrados


# ---------------------------------------------------------------- evaluación (sin escribir)
def _evaluar_residentes(db: Session, filas: list[dict], numeros: list[int]) -> list[imp.Fila]:
    evaluadas = [imp.validar_residente(n, v) for n, v in zip(numeros, filas)]
    vistos: dict[str, int] = {}
    for f in evaluadas:
        if f.accion == "error":
            continue
        correo = f.datos["email"]
        if correo in vistos:
            f.accion, f.mensaje = "error", f"El correo {correo} ya aparece en la fila {vistos[correo]}."
        else:
            vistos[correo] = f.numero
    existentes = _por_correos(db, [f.datos["email"] for f in evaluadas if f.accion != "error"])
    for f in evaluadas:
        if f.accion == "error":
            continue
        u = existentes.get(f.datos["email"])
        if u is None:
            f.accion = "crear"
            continue
        if u.rol != RolNombre.RESIDENTE.value:
            f.accion, f.mensaje = "error", f"Ese correo ya pertenece a un usuario con rol {u.rol}; no se modifica desde aquí."
            continue
        f.usuario_id = u.id
        cambios = [c for c, nuevo in f.datos.items() if c != "email" and getattr(u, c) != nuevo]
        f.accion = "actualizar" if cambios else "sin_cambios"
        f.mensaje = ("Cambia: " + ", ".join(c.replace("_asignado", "").replace("_", " ") for c in cambios)) if cambios else "Sin cambios."
    _validar_suma_coeficientes(db, evaluadas)
    return evaluadas


def _validar_suma_coeficientes(db: Session, evaluadas: list[imp.Fila]) -> None:
    """Los coeficientes de todos los apartamentos (los ya registrados + los de la planilla) no pueden pasar de 100 %."""
    con_coef = [f for f in evaluadas if f.accion != "error" and f.datos.get("coeficiente") is not None]
    if not con_coef:
        return
    residentes = coeficientes.residentes_activos(db)
    nuevos_por_id = {f.usuario_id: f.datos["coeficiente"] for f in con_coef if f.usuario_id}
    mapa: dict[str, float] = {}
    for u in residentes:
        clave = coeficientes.norm_apto(u.apartamento)
        valor = nuevos_por_id.get(u.id, u.coeficiente)
        if clave and valor:
            mapa[clave] = max(mapa.get(clave, 0.0), valor)
    for f in con_coef:
        if not f.usuario_id:
            clave = coeficientes.norm_apto(f.datos["apartamento"])
            mapa[clave] = max(mapa.get(clave, 0.0), f.datos["coeficiente"])
    total = sum(mapa.values())
    if total > coeficientes.TOTAL_MAXIMO + coeficientes.TOLERANCIA:
        raise HTTPException(status_code=400, detail=f"Los coeficientes (los ya registrados más los de la planilla) suman {total:.4f} %, más del 100 % permitido. Revisa la columna «coeficiente».")


def _evaluar_cartera(db: Session, filas: list[dict], numeros: list[int]) -> list[imp.Fila]:
    evaluadas = [imp.validar_cartera(n, v) for n, v in zip(numeros, filas)]
    residentes = (db.query(Usuario).join(Rol, Rol.id == Usuario.rol_id).filter(Rol.nombre == RolNombre.RESIDENTE.value).all())
    por_correo = {u.email.lower(): u for u in residentes}
    por_apto: dict[str, list[Usuario]] = {}
    for u in residentes:
        if u.esta_activo and u.apartamento:
            por_apto.setdefault(imp.clave_apartamento(u.apartamento), []).append(u)
    atendidos: dict[int, int] = {}
    for f in evaluadas:
        if f.accion == "error":
            continue
        email, apto = f.datos["email"], f.datos["apartamento"]
        u = por_correo.get(email) if email else None
        if u is None and apto:
            candidatos = por_apto.get(imp.clave_apartamento(apto), [])
            if len(candidatos) > 1:
                f.accion, f.mensaje = "error", f"El apartamento «{apto}» tiene {len(candidatos)} residentes; usa el correo para identificar a quién va el saldo."
                continue
            u = candidatos[0] if candidatos else None
        if u is None:
            f.accion, f.mensaje = "error", f"No encontré a quién pertenece ({email or apto}). Revisa el correo o el apartamento."
            continue
        if u.id in atendidos:
            f.accion, f.mensaje = "error", f"Ese apartamento ya aparece en la fila {atendidos[u.id]}."
            continue
        atendidos[u.id] = f.numero
        f.usuario_id = u.id
        f.datos.update(nombre=u.nombre_completo, email=u.email, apartamento=u.apartamento or "", saldo_anterior=u.saldo_pendiente)
        igual = u.saldo_pendiente == f.datos["saldo_pendiente"] and u.esta_al_dia == (f.datos["saldo_pendiente"] == 0)
        f.accion = "sin_cambios" if igual else "actualizar"
        if not igual:
            f.mensaje = f"Saldo: {u.saldo_pendiente:,} → {f.datos['saldo_pendiente']:,}".replace(",", ".")
    return evaluadas


def _procesar(db: Session, tipo: str, archivo: UploadFile) -> tuple[list[imp.Fila], str]:
    nombre = archivo.filename or "archivo"
    try:
        filas, numeros = imp.leer_tabla(nombre, _leer_subida(archivo), tipo)
    except imp.ErrorDeArchivo as e:
        raise HTTPException(status_code=400, detail=str(e))
    return (_evaluar_residentes if tipo == "residentes" else _evaluar_cartera)(db, filas, numeros), nombre


def _resumen(tipo: str, nombre: str, evaluadas: list[imp.Fila], aplicado: bool) -> ResumenImportacion:
    cuenta = {a: sum(1 for f in evaluadas if f.accion == a) for a in ("crear", "actualizar", "sin_cambios", "error")}
    errores = [f for f in evaluadas if f.accion == "error"]
    validas = [f for f in evaluadas if f.accion != "error"]
    mostradas = (errores + validas[:MAX_FILAS_LISTADAS])
    mostradas.sort(key=lambda f: f.numero)
    return ResumenImportacion(
        tipo=tipo, archivo=nombre, aplicado=aplicado, total=len(evaluadas), crear=cuenta["crear"], actualizar=cuenta["actualizar"],
        sin_cambios=cuenta["sin_cambios"], errores=cuenta["error"], filas_omitidas=max(0, len(validas) - MAX_FILAS_LISTADAS),
        filas=[FilaImportacion(fila=f.numero, accion=f.accion, mensaje=f.mensaje, nombre=f.datos.get("nombre_completo") or f.datos.get("nombre"),
                               email=f.datos.get("email") or None, apartamento=f.datos.get("apartamento") or None,
                               saldo_anterior=f.datos.get("saldo_anterior"), saldo_nuevo=f.datos.get("saldo_pendiente")) for f in mostradas])


# ---------------------------------------------------------------- endpoints
@router.get("/plantilla/{tipo}", summary="Descargar la plantilla de Excel",
            description="Solo **Administrador**. Excel con los encabezados exactos y una hoja de instrucciones. También se aceptan exportes del software contable "
                        "(Siigo, World Office, Alegra) siempre que tengan columnas con nombres equivalentes (correo/apartamento/saldo).",
            response_class=Response, responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}})
def plantilla(tipo: Tipo, _: Usuario = Depends(requiere_roles(ADMIN))):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    libro = Workbook()
    datos = libro.active
    datos.title = "Datos"
    if tipo == "residentes":
        columnas = ["nombre_completo", "email", "apartamento", "parqueadero", "valor_administracion", "coeficiente"]
        ayuda = [("nombre_completo", "Obligatoria. Nombre y apellidos (3 a 100 caracteres)."), ("email", "Obligatoria. Correo de la persona; es su usuario para entrar. No se puede repetir."),
                 ("apartamento", "Obligatoria. Por ejemplo: Torre 1 Apt 101."), ("parqueadero", "Opcional. Por ejemplo: P-12. Si va vacía no se cambia."),
                 ("valor_administracion", "Opcional. Cuota mensual en pesos, por ejemplo 180000. Si va vacía no se cambia."),
                 ("coeficiente", "Opcional pero necesaria para votar por coeficiente (Ley 675). Porcentaje de copropiedad del apartamento, por ejemplo 0,8523. Entre todos los apartamentos deben sumar 100. Si va vacía no se cambia.")]
        ejemplo = "Ana María Gómez | ana.gomez@correo.com | Torre 1 Apt 101 | P-12 | 180000 | 0,8523"
        notas = ["Cada fila con un correo NUEVO crea una cuenta de Residente con una clave temporal (se muestra una sola vez al terminar). Debe cambiarla al entrar.",
                 "Si el correo ya existe como Residente, se actualizan sus datos (nombre, apartamento, parqueadero, cuota). Nunca se cambia su clave ni su rol.",
                 "Si el correo pertenece a un guardia, administrador o inquilino, esa fila se rechaza."]
    else:
        columnas = ["email", "apartamento", "saldo_pendiente"]
        ayuda = [("email", "Recomendada. Correo del residente. Si va vacía se usa el apartamento."), ("apartamento", "Alternativa al correo. Debe coincidir con el apartamento registrado (no importan mayúsculas ni tildes)."),
                 ("saldo_pendiente", "Obligatoria. Lo que debe hoy, en pesos. Acepta $ 1.250.000, 1250000 o 1,250,000. Usa 0 para quien está al día.")]
        ejemplo = "ana.gomez@correo.com | Torre 1 Apt 101 | 360000"
        notas = ["Reemplaza el saldo de cada apartamento por el de la planilla: saldo mayor a 0 = en mora (no puede reservar); 0 = al día.",
                 "Los apartamentos que NO aparecen en la planilla no se tocan.",
                 "Sirve el exporte de Siigo, World Office o Alegra: basta con que tenga columnas de correo o apartamento y de saldo. Los títulos sobre la tabla se ignoran."]
    datos.append(columnas)
    for celda in datos[1]:
        celda.font, celda.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="053550")
    for i, c in enumerate(columnas, start=1):
        datos.column_dimensions[chr(64 + i)].width = max(18, len(c) + 4)
    datos.freeze_panes = "A2"
    guia = libro.create_sheet("Instrucciones")
    guia.append(["Columna", "Qué poner"])
    guia.append(["", ""])
    for c, t in ayuda:
        guia.append([c, t])
    guia.append(["", ""])
    guia.append(["Ejemplo de una fila", ejemplo])
    guia.append(["", ""])
    for n in notas:
        guia.append(["Importante", n])
    guia.append(["", ""])
    guia.append(["Límites", f"Máximo {imp.MAX_FILAS} filas por archivo. Escribe los datos en la hoja «Datos», debajo de los encabezados, y borra las filas de ejemplo si copiaste alguna."])
    guia["A1"].font = guia["B1"].font = Font(bold=True)
    guia.column_dimensions["A"].width, guia.column_dimensions["B"].width = 24, 110
    for fila in guia.iter_rows():
        for c in fila:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    buf = io.BytesIO()
    libro.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="plantilla_{tipo}.xlsx"', "Cache-Control": "no-store"})


@router.post("/{tipo}/vista-previa", response_model=ResumenImportacion, summary="Revisar el archivo sin guardar nada",
             description="Solo **Administrador**. Valida todas las filas y devuelve qué se **crearía**, **actualizaría** o dejaría **sin cambios**, y los errores fila por fila. "
                         "No modifica la base de datos.", responses={400: {"description": "Archivo ilegible o sin los encabezados"}, 413: {"description": "Archivo demasiado grande"}})
def vista_previa(tipo: Tipo, archivo: UploadFile = File(...), db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(ADMIN))):
    evaluadas, nombre = _procesar(db, tipo, archivo)
    return _resumen(tipo, nombre, evaluadas, aplicado=False)


@router.post("/{tipo}/aplicar", response_model=ResumenImportacion, summary="Guardar la importación",
             description="Solo **Administrador**. Vuelve a validar el archivo y lo guarda en **una sola transacción** (o todo o nada). Si hay filas con errores se rechaza "
                         "salvo que envíes `omitir_errores=true` (entonces se guardan solo las válidas). En residentes, devuelve las **claves temporales** de las cuentas nuevas: "
                         "se muestran una sola vez.", responses={400: {"description": "Hay filas con errores o el archivo no sirve"}, 409: {"description": "Un correo se creó en paralelo"}})
def aplicar(tipo: Tipo, omitir_errores: bool = Query(False), archivo: UploadFile = File(...), db: Session = Depends(get_db),
            admin: Usuario = Depends(requiere_roles(ADMIN))):
    evaluadas, nombre = _procesar(db, tipo, archivo)
    errores = sum(1 for f in evaluadas if f.accion == "error")
    if errores and not omitir_errores:
        raise HTTPException(status_code=400, detail=f"El archivo tiene {errores} fila(s) con errores. Corrígelas y vuelve a subirlo, o importa solo las filas válidas.")
    resumen = _resumen(tipo, nombre, evaluadas, aplicado=True)
    if tipo == "residentes":
        resumen.credenciales = _guardar_residentes(db, evaluadas)
        detalle = f"{nombre}: {resumen.crear} creados, {resumen.actualizar} actualizados, {errores} omitidos"
        auditar(db, admin, "Importó el censo de residentes", "Usuario", None, detalle)
    else:
        resumen.entraron_en_mora, resumen.salieron_de_mora = _guardar_cartera(db, evaluadas)
        detalle = f"{nombre}: {resumen.actualizar} saldos actualizados, {resumen.entraron_en_mora} entraron en mora, {resumen.salieron_de_mora} salieron, {errores} omitidos"
        auditar(db, admin, "Importó la cartera", "Cartera", None, detalle)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Alguien creó uno de esos correos mientras importabas. Vuelve a subir el archivo.")
    return resumen


def _guardar_residentes(db: Session, evaluadas: list[imp.Fila]) -> list[CredencialNueva]:
    rol = db.query(Rol).filter(Rol.nombre == RolNombre.RESIDENTE.value).one()
    por_id = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_([f.usuario_id for f in evaluadas if f.accion == "actualizar"] or [0])).all()}
    credenciales = []
    for f in evaluadas:
        if f.accion == "crear":
            clave = secrets.token_urlsafe(9)                       # 12 caracteres, ~72 bits: igual que «restablecer clave»
            # Clave TEMPORAL: se cifra con 8 rondas de bcrypt (≈16 veces más rápido que las 12 normales) para que importar 200 cuentas tarde
            # segundos y no minutos. Es seguro porque es aleatoria de 72 bits y la persona está obligada a cambiarla al entrar (ahí se guarda con las 12 rondas).
            db.add(Usuario(nombre_completo=f.datos["nombre_completo"], email=f.datos["email"], password_encriptada=encriptar_password(clave, rondas=8),
                           rol_id=rol.id, apartamento=f.datos["apartamento"], debe_cambiar_password=True,
                           **{k: v for k, v in f.datos.items() if k in ("parqueadero_asignado", "valor_administracion", "coeficiente")}))
            credenciales.append(CredencialNueva(nombre_completo=f.datos["nombre_completo"], email=f.datos["email"], apartamento=f.datos["apartamento"], clave_temporal=clave))
        elif f.accion == "actualizar":
            u = por_id[f.usuario_id]
            for campo, valor in f.datos.items():
                if campo != "email":
                    setattr(u, campo, valor)
    return credenciales


def _guardar_cartera(db: Session, evaluadas: list[imp.Fila]) -> tuple[int, int]:
    por_id = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_([f.usuario_id for f in evaluadas if f.accion == "actualizar"] or [0])).all()}
    entraron = salieron = 0
    for f in evaluadas:
        if f.accion != "actualizar":
            continue
        u, saldo = por_id[f.usuario_id], f.datos["saldo_pendiente"]
        if u.esta_al_dia and saldo > 0:
            entraron += 1
        elif not u.esta_al_dia and saldo == 0:
            salieron += 1
        u.saldo_pendiente, u.esta_al_dia = saldo, saldo == 0
    return entraron, salieron
