# Versión 4.6 · Asambleas de copropietarios (Ley 675 de 2001) — Fases 1 y 2

Agrega un módulo nuevo **sin cambiar el comportamiento de nada existente** (las 523 pruebas anteriores siguen pasando). Requiere **una migración (0022)** y trae 50 pruebas nuevas.

## Qué se agregó (y por qué)
La asamblea **envuelve** a tu motor de votaciones: primero hay que poder convocar, registrar quién está, sumar el quórum y dejar evidencia. Las votaciones dentro de la asamblea llegan en la Fase 3.

| Pieza | Qué hace | Por qué |
|---|---|---|
| **Unidades** (`/unidades`) | Cada apartamento con su coeficiente; es la **base del quórum** (debe sumar 100 %). Los apartamentos con residentes se copian solos desde «Usuarios»; los propietarios **sin cuenta** se agregan a mano. | Antes el 100 % salía solo de los residentes con cuenta: con propietarios sin app, el quórum y el 70 % habrían salido mal. |
| **Asamblea** (`/asambleas`) | Borrador → Convocada → En sesión → Cerrada (o Cancelada). Ordinaria/extraordinaria; presencial, virtual o mixta. | Es el ciclo de vida legal de una reunión. |
| **Convocatoria** | Valida plazos, exige orden del día, medios tecnológicos (si es virtual/mixta) y estados financieros (si es ordinaria). Guarda la **huella SHA-256** de lo enviado y la **relación de morosos**. Avisa por la app y deja constancia **por unidad**. PDF descargable para quien no usa la app. | Art. 39 y 41 de la Ley 675; Decreto 398 de 2020. |
| **Bitácora encadenada** | Cada movimiento queda con fecha/hora y la huella del anterior. `GET /asambleas/{id}/bitacora` dice si la cadena sigue íntegra. | Evidencia ante una impugnación (Art. 49). Es *evidencia fuerte*, no «inalterable» absoluta: quien controle la base de datos podría alterarla, pero se rompería la cadena y se vería. |
| **Acreditación** | Administrador o guardia registran entradas y salidas (presencial o virtual); el residente se conecta solo en las virtuales. El coeficiente se **copia** al acreditar. Quórum en vivo y **pantalla grande**. | El caos real ocurre en los primeros 45 minutos. La «foto» del coeficiente evita que un cambio posterior altere el quórum de esa reunión. |
| **Poderes** | El propietario sube PDF o foto; el administrador aprueba/rechaza con motivo. Límite de poderes por persona; el personal del conjunto no puede recibir poderes. | Quita las filas en la puerta y protege contra conflictos de interés. |
| **Instalar / sin quórum / 2.ª convocatoria** | 1.ª: más del 50 % de los coeficientes. 2.ª: tercer día hábil siguiente a las 8 p. m. (con festivos de Colombia) y número plural (2 o más unidades). | Art. 41 y 45. |

## Archivos nuevos y modificados
**Nuevos:** `alembic/versions/0022_asambleas.py` · `app/asambleas.py` (reglas) · `app/unidades.py` · `app/calendario_co.py` (festivos y días hábiles) · `app/routers/asambleas.py` · `app/schemas/asambleas.py` · `frontend/js/vistas/asambleas.js` · `tests/test_v46_asambleas.py` · este archivo.
**Modificados (solo se agregó):** `app/models.py` (6 tablas) · `app/constantes.py` (enums) · `app/config.py` (6 variables) · `app/main.py` (rutas, etiquetas, versión 4.6.0) · `app/routers/documentos.py` (no deja borrar un documento que acompañó una convocatoria enviada) · `frontend/js/app.js` (ruta) · `vistas/mas.js` (menú) · `ui.js` (icono y colores de estado) · `api.js` (los datos en vivo no se guardan en caché) · `estilos.css` (bloque «VERSIÓN 4.6») · `.env.example`.

## Variables de entorno (todas opcionales; ya traen valor)
`ASAMBLEA_DIAS_ORDINARIA=15` · `ASAMBLEA_DIAS_EXTRAORDINARIA=5` · `ASAMBLEA_MAX_PODERES=2` · `ASAMBLEA_SABADO_HABIL=0` · `ASAMBLEA_EXIGE_FINANCIEROS=1` · `ASAMBLEA_BLOQUEA_PODER_STAFF=1`

## Supuestos que debe validar un abogado de propiedad horizontal
Son decisiones **prudentes**, no verdades legales. Si tu reglamento dice otra cosa, el reglamento manda:
1. **15 días «completos»**: no cuentan ni el día del envío ni el de la reunión (se exige una diferencia de 16 días de calendario). Es una lectura conservadora del Art. 39.
2. **Extraordinaria: 5 días** de anticipación: la ley no fija un mínimo; revisa tu reglamento (`ASAMBLEA_DIAS_EXTRAORDINARIA`).
3. **Segunda convocatoria**: tercer día hábil después de la primera, 8 p. m., sin contar sábados (`ASAMBLEA_SABADO_HABIL=1` los cuenta). Se puede escribir otra fecha al crear.
4. **«Número plural»** = al menos 2 unidades presentes.
5. **Mora**: por defecto **no** quita el voto (la ley no lo prohíbe por sí sola). Solo se activa por asamblea si el reglamento lo dice.
6. **Apoderados**: máximo 2 por persona y el administrador/personal no reciben poderes. Son reglas del reglamento y buena práctica, no del texto de la ley.
7. **Convocatoria por la app** deja constancia, pero no reemplaza la entrega por el medio que el reglamento exija. Las unidades sin cuenta quedan como «Pendiente» hasta registrar la entrega manual.
8. **Reuniones virtuales**: la app registra conexiones y horas; la **grabación** de la sesión (prueba principal) la hace la herramienta de videollamada.
9. **Decisiones del 70 % no pueden tomarse en reuniones no presenciales** (Art. 46). Esto se bloqueará en la Fase 3, cuando se conecten las votaciones.

## Qué NO está todavía (Fases 3 y 4)
Votaciones ligadas a la asamblea (mayoría simple o del 70 %, voto nominal/secreto, fotos de quórum por pregunta) · elección de consejo con varios cupos · candidatos en vivo · acta PDF con cierre y congelado.

## Cómo volver atrás
`alembic downgrade 0021` borra solo las 6 tablas nuevas (las demás no se tocan). Luego revierte los archivos modificados con `git`.

## Qué hacer después (en este orden)
1. **Migración local:** `alembic upgrade head` (aplica la 0022). Es segura aunque la corras dos veces.
2. **Probar en local** (`.\iniciar-demo.bat`): entra como administrador → *Más → Asambleas*. Primero **Unidades y coeficientes** (deben sumar 100 %), luego crea una asamblea y recórrela con un residente y un guardia.
3. **Pruebas:** `python -m pytest -q` y `node --test tests/js/atras.test.mjs`.
4. **GitHub:** `git add .` · `git commit -m "v4.6: asambleas de copropietarios (Ley 675) fases 1 y 2"` · `git push`.
5. **Despliegue:** Render ejecuta `alembic upgrade head` al arrancar (aplica la 0022 en Supabase). Espera a que termine y revisa el CI.
6. **Celular:** cierra la PWA por completo y ábrela dos veces para que cargue la versión nueva.
7. **Producción:** como administrador abre *Asambleas → Unidades y coeficientes* y confirma que suman 100 %.
8. **Para una asamblea real:** Render gratis se duerme a los 15 minutos; usa un plan que no se duerma ese día.
