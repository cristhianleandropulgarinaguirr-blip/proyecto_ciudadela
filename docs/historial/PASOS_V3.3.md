# Versión 3.3 — rol Inquilino: qué cambió y cómo ponerla a funcionar

## Qué cambió
1. **Rol nuevo «Inquilino»** con su propio color (violeta, claro y oscuro) y permisos acotados: reserva zonas, reporta daños, recibe paquetes, avisa visitas (tope de 5) y radica PQRS; **no** ve cartera, pagos ni votaciones, y de los documentos solo ve Reglamento y Circular.
2. **Contrato de arrendamiento** (tabla `arrendamientos`): lo registra el propietario, lo aprueba el administrador y el acceso **vence solo** con la fecha de fin.
3. **Mora heredada:** si el propietario está en mora, las reservas de su inquilino también se bloquean.
4. **Paquetes:** el inquilino ve solo los suyos (antes la regla de «ver solo lo mío» miraba únicamente al rol Residente).
5. Archivos nuevos: `app/arrendamientos.py`, `app/routers/arrendamientos.py`, `app/schemas/arrendamientos.py`, `alembic/versions/0014_rol_inquilino_arrendamientos.py`, `frontend/js/vistas/inquilinos.js`, `tests/test_arrendamientos.py`.

## Pasos
1. **Migración de base de datos: SÍ hace falta.** En tu PC: `alembic upgrade head` (crea la tabla `arrendamientos` y el rol «Inquilino»). En Render se aplica sola al desplegar (el `startCommand` ya la ejecuta).
2. Probar en tu PC: `pytest -q` (deben pasar 232 pruebas: las 212 anteriores + 20 nuevas) y luego `iniciar.bat`.
3. Prueba a mano con tres cuentas: propietario (registra un inquilino) → administrador (lo aprueba y copia la clave temporal) → inquilino (entra, cambia la clave y revisa que no vea Cartera ni Votaciones). Revisa el color violeta en modo claro y oscuro.
4. Subir a GitHub: `git add .` · `git commit -m "v3.3: rol Inquilino con arrendamientos"` · `git push`.
5. Render despliega solo. Cuando termine, entra como administrador y confirma que aparece «Arrendamientos» en el menú.
6. Celular: cerrar y abrir la app para que se instale la versión nueva de la PWA.
