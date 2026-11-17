# Versión 3.4 — Fase 3 del rol Inquilino (permisos delegables) + arreglo del despliegue

## 1. El arreglo del despliegue (ya venía en la 3.3.1)
**Qué falló en Render:** `IntegrityError: duplicate key value violates unique constraint "roles_pkey"`.
**Por qué:** la migración `0002` creó los roles Administrador, Residente y Guardia con ids puestos a mano (1, 2, 3). En PostgreSQL eso deja el contador automático de ids (`roles_id_seq`) atrasado. Cuando se insertó «Inquilino» sin indicar id, PostgreSQL le asignó un número que ya estaba ocupado. SQLite no tiene ese problema, por eso las pruebas locales pasaban.
**Cómo se arregló:**
- `alembic/versions/0014_...`: el rol nuevo se inserta con id explícito (el mayor + 1) y al final se alinea el contador (`setval`).
- `app/seed.py`: `asegurar_roles` alinea el contador antes de insertar y le da id a cada rol al momento.
- Probado en un PostgreSQL real en 3 escenarios: base nueva, base en 0013 con el contador atrasado (igual que Render) y contador desalineado a propósito. Los tres terminan con los 4 roles y el contador bien.
- Prueba nueva de regresión: `test_el_seed_crea_el_rol_inquilino_con_id_propio_si_falta`.

## 2. Qué trae la Fase 3
1. Dos permisos que el **propietario** le puede dar a su inquilino, apagados por defecto: **pagar la administración** y **votar** (columnas `puede_pagar` y `puede_votar` en `arrendamientos`, migración `0015`).
2. `PATCH /arrendamientos/{id}/permisos`: solo el propietario del contrato.
3. Pagos: el inquilino con el permiso ve la cartera del apartamento, paga y descarga comprobantes; todo queda a nombre del propietario y se le avisa.
4. Votaciones: el inquilino con el permiso vota por el apartamento (un solo voto por apartamento) y hereda la mora del propietario.
5. `/usuarios/me` devuelve `delegaciones` y el menú del inquilino muestra «Pagos del apartamento» y «Votaciones» solo si las tiene.
6. En «Mis inquilinos» aparecen los dos interruptores; el inicio del inquilino muestra accesos según lo delegado.

## 3. Pasos para dejarlo funcionando
1. **Migración: SÍ.** En tu PC: `alembic upgrade head` (aplica 0014 y 0015). En Render se aplica sola al desplegar, porque el comando de inicio ya ejecuta `alembic upgrade head` antes del seed.
2. Pruebas: `pytest -q` → deben pasar **247**.
3. Prueba a mano: propietario registra inquilino → administrador aprueba → propietario activa «Votar» → administrador crea una votación → el inquilino entra, vota, y el propietario comprueba que ya no puede votar esa consulta. Repite con «Pagar» (el administrador registra una deuda al propietario).
4. GitHub: `git add .` · `git commit -m "v3.4: permisos delegables al inquilino y arreglo de roles en PostgreSQL"` · `git push`.
5. Render despliega solo. Revisa los logs: deben aparecer «Running upgrade 0013 -> 0014» y «0014 -> 0015» y, después, el arranque de uvicorn sin errores.
6. Celular: cerrar y abrir la app para instalar la versión nueva. El inquilino debe cerrar y abrir la app para ver un permiso recién delegado en su menú.
