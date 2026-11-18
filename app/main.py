# app/main.py
import hashlib
import json
import logging

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app import config, marca
from app.routers import (
    anuncios, arrendamientos, asistente, auditoria, auth, comercio, dashboard, demo, documentos, emergencias, importaciones, modulos, notificaciones, paquetes, pagos_simulados, paz_y_salvo, pqrs, push, qr, reportes,
    publico, sincronizacion, trasteos, usuarios, visitantes, votaciones,
)

logging.basicConfig(level=logging.INFO)

DESCRIPCION = """
API para la gestión de un **conjunto residencial** (propiedad horizontal).

### Cómo probar las rutas protegidas
1. Inicia sesión en `POST /auth/login` (o pulsa el botón **Authorize** 🔒 e ingresa correo y contraseña).
2. Swagger enviará el token JWT automáticamente en cada petición.

### Roles
| Rol | Qué puede hacer |
|---|---|
| **Administrador** | Todo: usuarios, aprobar reservas, estado de los daños, cartera, portería, auditoría, emergencias, PQRS, documentos y reportes en Excel |
| **Residente** | Reservar zonas, reportar daños, pagar su administración, crear pases QR, autorizar visitantes frecuentes, ver sus paquetes, radicar PQRS, descargar documentos y anunciar su negocio |
| **Inquilino** | Lo registra su propietario y lo aprueba el administrador; el acceso vence con el contrato. Reservar zonas (si el apartamento está al día), reportar daños, recibir paquetes, crear pases QR y visitantes (hasta 5), radicar PQRS, ver reglamento y circulares. **Sin** comercio propio. Cartera/pagos y votaciones **solo si su propietario se los delega** (y por defecto no puede ninguno) |
| **Guardia** | Controlar vehículos y visitantes (también escaneando QR), registrar y entregar paquetes, ver reservas |

Errores de seguridad: **401** = no has iniciado sesión o el token expiró · **403** = tu rol no tiene permiso.
"""

TAGS = [
    {"name": "Autenticación", "description": "Inicio de sesión: token de acceso corto (JWT) + cookie de renovación HttpOnly rotativa. Las cuentas las crea el administrador."},
    {"name": "Usuarios (Administración)", "description": "Gestión de usuarios y roles. Solo administrador."},
    {"name": "Reservas de Áreas Comunes", "description": "Solicitud y aprobación de zonas comunes."},
    {"name": "Gestión de Incidencias y Daños", "description": "Reportes de daños con foto."},
    {"name": "Recaudo de Administración", "description": "Estado de cuenta, deuda y pagos."},
    {"name": "Anuncios y Comunicados", "description": "Cartelera: reuniones, eventos y avisos con confirmación de asistencia."},
    {"name": "Códigos QR", "description": "Carnet QR de cada usuario y pases QR para visitantes; escaneo en portería con bitácora."},
    {"name": "Comercio y Publicidad", "description": "Directorio de negocios de los vecinos: anuncios de pago con revisión del administrador."},
    {"name": "Visitantes Autorizados", "description": "Personas de confianza que el residente deja autorizadas; el guardia las verifica y registra su ingreso y salida a pie."},
    {"name": "Paquetes y Correspondencia", "description": "Portería registra lo que llega, el residente lo ve en la app y se registra la entrega."},
    {"name": "Contactos de Emergencia", "description": "Directorio de emergencias del conjunto: lo ven todos, lo edita el administrador."},
    {"name": "PQRS", "description": "Peticiones, quejas, reclamos y sugerencias: el residente radica y la administración responde."},
    {"name": "Asistente de IA", "description": "Borradores con IA para PQRS, daños y anuncios. Solo redacta: una persona revisa y envía con los formularios normales."},
    {"name": "Documentos del Conjunto", "description": "Reglamento, actas y circulares en PDF: los sube el administrador y los descargan todos."},
    {"name": "Notificaciones", "description": "La campana de la app: avisos de paquetes, PQRS, reservas, anuncios y documentos."},
    {"name": "Reportes", "description": "Excel para el administrador y PDF del estado de cuenta."},
    {"name": "Auditoría", "description": "Bitácora de quién hizo qué y cuándo (solo administrador)."},
    {"name": "Control de Parqueaderos", "description": "Portería: ingreso, salida e historial de vehículos visitantes, y sincronización de lo registrado sin internet."},
    {"name": "Arrendamientos (Inquilinos)", "description": "El propietario registra a su inquilino, el administrador lo aprueba y el acceso vence con el contrato."},
    {"name": "Pase público (sin sesión)", "description": "La página que abre el visitante con el enlace de su pase: QR, PIN, «Cómo llegar» y avisos «Estoy en camino / Llegué». Sin sesión; protegida por un token imposible de adivinar y por límites de uso."},
    {"name": "Carga masiva (Excel/CSV)", "description": "El administrador sube el censo de apartamentos y la cartera mensual desde Excel o CSV: primero una vista previa sin guardar nada, luego se aplica en una sola transacción."},
    {"name": "Indicadores (KPIs)", "description": "Números para la pantalla de indicadores del administrador: cartera, zonas más reservadas, tiempos de respuesta de PQRS y flujo de visitantes por hora."},
    {"name": "Paz y salvo", "description": "Certificado en PDF con código QR de verificación: se emite solo si el apartamento está al día y cualquiera puede comprobar su autenticidad escaneando el QR."},
    {"name": "Pagos simulados (pasarela de pruebas)", "description": "Pasarela de PRUEBAS tipo Wompi/PSE (solo con PAGOS_SIMULADOS=1): crear el intento, pagar con PSE, tarjeta o Nequi de prueba y consultar el estado. No mueve dinero."},
    {"name": "Votaciones", "description": "Consultas y votaciones del conjunto: voto secreto, un voto por apartamento, resultados al cerrar. Opción de votar por coeficiente de copropiedad (Ley 675) con quórum."},
    {"name": "Trasteos", "description": "Mudanzas: el residente solicita, el sistema valida el paz y salvo (en las salidas), el administrador aprueba, se alerta a la portería y el guardia registra el inicio y el fin."},
    {"name": "Presentación comercial (demo)", "description": "El botón «Solicitar demo» de la landing: guarda el contacto (sin sesión, muy limitado contra abuso) y el administrador lo gestiona."},
]

# Las tablas se crean con migraciones de Alembic (alembic upgrade head), no aquí.
# Con DOCS_ACTIVAS=0 las tres rutas de documentación desaparecen (responden 404), como si no existieran.
app = FastAPI(title="Mi Proyecto SENA API – Propiedad Horizontal", description=DESCRIPCION,
              version="4.4.0", openapi_tags=TAGS,
              docs_url="/docs" if config.DOCS_ACTIVAS else None,
              redoc_url="/redoc" if config.DOCS_ACTIVAS else None,
              openapi_url="/openapi.json" if config.DOCS_ACTIVAS else None)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(modulos.router)
app.include_router(anuncios.router)
app.include_router(qr.router)
app.include_router(comercio.router)
app.include_router(visitantes.router)
app.include_router(paquetes.router)
app.include_router(emergencias.router)
app.include_router(pqrs.router)
app.include_router(asistente.router)
app.include_router(documentos.router)
app.include_router(notificaciones.router)
app.include_router(reportes.router)
app.include_router(auditoria.router)
app.include_router(votaciones.router)
app.include_router(arrendamientos.router)
app.include_router(push.router)
app.include_router(sincronizacion.router)
app.include_router(publico.router)
app.include_router(importaciones.router)
app.include_router(dashboard.router)
app.include_router(paz_y_salvo.router)
app.include_router(trasteos.router)
app.include_router(demo.router)
app.include_router(pagos_simulados.router)


# Frontend (HTML/CSS/JS) servido por la misma API: así comparten origen y no hace falta configurar CORS.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Lo que el service worker guarda en el celular al INSTALAR (el «núcleo» para que la interfaz abra sin pedir nada más).
# Lo demás (fondos, iconos de la app, lector jsQR) se guarda sola la primera vez que se usa.
_EXT_NUCLEO = {".html", ".js", ".css", ".webmanifest"}
_IMG_NUCLEO = {"icono.png", "icono-crema.png", "logo-crema.png", "favicon.png"}


def _archivos_de_la_app() -> list[Path]:
    return sorted(p for p in FRONTEND_DIR.rglob("*") if p.is_file() and p.name != "sw.js" and "vendor" not in p.parts and "pase" not in p.parts and "verificar" not in p.parts
                  and (p.suffix in _EXT_NUCLEO or (p.parent.name == "img" and p.name in _IMG_NUCLEO)))


def _service_worker() -> str:
    """sw.js con la lista de archivos y un código de versión que cambia SOLO cuando cambia algún archivo del frontend.
    Así nadie tiene que acordarse de subir un número a mano: cada despliegue con cambios renueva la caché de todos."""
    huella = hashlib.sha256()
    huella.update(marca.huella().encode())       # v4.0: si cambia el nombre, el color o un logo del cliente, todos los celulares descargan la versión nueva
    for p in sorted(q for q in FRONTEND_DIR.rglob("*") if q.is_file()):      # TODOS los archivos: si cambia cualquiera, cambia la versión
        huella.update(p.relative_to(FRONTEND_DIR).as_posix().encode())
        huella.update(p.read_bytes())
    rutas = ["./"]
    for p in _archivos_de_la_app():
        rel = p.relative_to(FRONTEND_DIR).as_posix()
        rutas.append("./" if rel == "index.html" else rel)
    plantilla = (FRONTEND_DIR / "sw.js").read_text(encoding="utf-8")
    return (plantilla.replace("__VERSION__", huella.hexdigest()[:12]).replace("__ARCHIVOS__", json.dumps(sorted(set(rutas))))
            .replace("__NOMBRE__", json.dumps(marca.nombre(), ensure_ascii=False).replace("<", "\\u003c")))


_sw_cache: dict[str, str] = {}


@app.get("/app/sw.js", include_in_schema=False)
def service_worker():
    # Se calcula una vez por arranque del servidor (los archivos no cambian mientras corre).
    if "sw" not in _sw_cache:
        _sw_cache["sw"] = _service_worker()
    return Response(_sw_cache["sw"], media_type="application/javascript", headers={"Service-Worker-Allowed": "/app/"})


# v4.0 · White-label: la página de la app y el manifest se arman al vuelo con la marca del cliente (nombre, color, textos).
# Van ANTES del montaje estático para tener prioridad sobre frontend/index.html y frontend/manifest.webmanifest.
@app.get("/app/", include_in_schema=False)
@app.get("/app/index.html", include_in_schema=False)
def pagina_de_la_app():
    return HTMLResponse(marca.aplicar_a_html((FRONTEND_DIR / "index.html").read_text(encoding="utf-8")))


@app.get("/app/manifest.webmanifest", include_in_schema=False)
def manifest_de_la_app():
    return Response(marca.manifest((FRONTEND_DIR / "manifest.webmanifest").read_text(encoding="utf-8")), media_type="application/manifest+json")


class AppEstatica(StaticFiles):
    """Igual que StaticFiles, pero si el cliente puso su logo en la carpeta marca/ (mismo nombre que en frontend/img), se sirve ese."""

    async def get_response(self, path: str, scope):
        path_url = path.replace("\\", "/")        # en Windows Starlette entrega «img\\icono.png» (barra invertida): se normaliza para que funcione igual en todos los sistemas
        if path_url.startswith("img/"):
            propio = marca.ruta_imagen_personalizada(path_url[len("img/"):])
            if propio is not None:
                if scope["method"] not in ("GET", "HEAD"):
                    raise HTTPException(status_code=405)
                return FileResponse(propio)
        return await super().get_response(path, scope)


app.mount("/app", AppEstatica(directory=FRONTEND_DIR, html=True), name="frontend")

# v4.0 · Landing comercial: la página está en landing/index.html y sus archivos (css/js) en landing/recursos/, servidos en /landing.
LANDING_DIR = Path(__file__).resolve().parent.parent / "landing"
LANDING_PAGINA = LANDING_DIR / "index.html"
app.mount("/landing", StaticFiles(directory=LANDING_DIR / "recursos"), name="landing")


class GZipSelectivo:
    """Comprime texto (HTML, JS, CSS, JSON) y deja pasar tal cual lo que ya viene comprimido (imágenes, PDF): comprimirlo otra vez solo gasta CPU."""
    _SIN_COMPRIMIR = (".png", ".jpg", ".jpeg", ".webp", ".pdf", ".ico", ".woff2")

    def __init__(self, app):
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=700, compresslevel=6)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            ruta = scope["path"].lower()
            if ruta.endswith(self._SIN_COMPRIMIR) or ruta.endswith(("/foto", "/imagen")):
                return await self.app(scope, receive, send)
        await self.gzip(scope, receive, send)


# La landing hace lo mismo que la app (fuentes de Google, nada inline en JS) y además puede abrir WhatsApp (es un enlace, no una carga).
CSP_LANDING = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
               "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
CSP_APP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
           "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
           "worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    """Cabeceras básicas en todas las respuestas. El service worker y el manifest no se guardan en caché para que las actualizaciones lleguen."""
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "same-origin")
    respuesta.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")   # la cámara la usa el escáner QR
    if request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
        respuesta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.url.path.startswith("/app"):
        # Política de contenido: solo se ejecuta JavaScript propio. Si alguna vez se colara código ajeno en la página, el navegador lo bloquea.
        respuesta.headers.setdefault("Content-Security-Policy", CSP_APP)
    if request.url.path == "/" or request.url.path.startswith("/landing"):
        respuesta.headers.setdefault("Content-Security-Policy", CSP_LANDING)
        respuesta.headers["Cache-Control"] = "no-cache"
    # Toda la app (html, js, css) se revalida en cada carga: si no cambió responde 304 (rápido); si cambió, llega la versión nueva.
    if request.url.path.startswith("/app"):
        # Imágenes de la interfaz (logos, fondos, iconos): casi nunca cambian → una semana en caché. El resto se revalida.
        if request.url.path.startswith("/app/img/"):
            respuesta.headers["Cache-Control"] = "public, max-age=604800"
        else:
            respuesta.headers["Cache-Control"] = "no-cache"
    return respuesta


# Se agrega al final para quedar como capa más externa (comprime también lo que añaden los demás middlewares).
app.add_middleware(GZipSelectivo)


@app.get("/", include_in_schema=False)
def inicio():
    """v4.0 · La raíz muestra la landing comercial (con «Solicitar demo»); la aplicación vive en /app/ y la documentación de la API en /docs.
    Con LANDING_ACTIVA=0 (la app de un cliente ya contratado) la raíz lleva directo a la aplicación, como antes."""
    if not config.LANDING_ACTIVA or not LANDING_PAGINA.is_file():
        return RedirectResponse(url="/app/")
    extra = {"whatsapp": config.DEMO_WHATSAPP, "correo_ventas": config.DEMO_CORREO, "contacto": config.DEMO_CONTACTO}
    return HTMLResponse(marca.aplicar_a_html(LANDING_PAGINA.read_text(encoding="utf-8"), extra))


@app.get("/salud", tags=["Estado"], summary="Verificar que el servidor está corriendo")
def salud():
    return {"mensaje": "¡Servidor corriendo! Documentación en /docs"}
