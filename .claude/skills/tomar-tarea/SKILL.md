---
name: tomar-tarea
description: Toma la próxima tarea del GitHub Project del Observatorio, la implementa, la prueba, abre el PR, lo hace revisar y lo mergea si pasa todos los controles. Usar cuando el mantenedor pide "tomá una tarea", "seguí con el proyecto" o invoca /tomar-tarea.
argument-hint: "[número de issue opcional]"
disable-model-invocation: true
---

# Tomar una tarea y llevarla hasta el merge

Trabajás sin supervisión. El mantenedor autorizó de antemano: crear ramas, commitear, pushear ramas, abrir PRs, comentar issues, mover tarjetas del Project y mergear PRs **que cumplan todas las condiciones de la sección 7**. Cualquier otra cosa fuera de este procedimiento no está autorizada.

Hacé **una sola tarea por ejecución**. Al terminar, reportá y pará con la línea `RESULTADO:` de la sección final.

## Configuración

- Repositorio: el del directorio actual (`gh repo view --json nameWithOwner`).
- Project: número y dueño en `.claude/proyecto.json` (`{"owner": "...", "numero": N}`). Si no existe, frená y pedilo.
- Documentos que mandan: `CLAUDE.md`, `docs/SYSTEM.md`, `docs/ACCEPTANCE_CRITERIA.md`, `docs/PLAN.md`.

## 1. Elegir la tarea

Si se pasó un número (`$ARGUMENTS`), usá ese issue. Si ese issue tiene la etiqueta `necesita-humano` porque dejaste preguntas (comentario con `<!-- tomar-tarea:preguntas -->`) y hay respuesta en un comentario posterior, sacá la etiqueta y retomalo usando esas respuestas. Como vos y el mantenedor comentan con la misma cuenta de GitHub, la autoría no sirve para distinguirlos: cuenta como respuesta un comentario posterior que **no** empieza con `<!-- tomar-tarea`, o uno que empieza con `<!-- trabajar:respuestas -->` (respuestas que `/trabajar` copió del chat). Todo comentario tuyo empieza con `<!-- tomar-tarea -->` (o `<!-- tomar-tarea:preguntas -->`). Si todavía no hay respuesta, terminá con `RESULTADO: pregunta`. Si no se pasó número:

1. `gh project item-list <numero> --owner <owner> --format json --limit 200`
2. Candidatas: Estado = "Por hacer", tipo `historia`, `tarea` o `bug` (nunca una `épica` entera), sin etiqueta `necesita-humano` ni `regla-de-datos`, sin issues bloqueantes abiertos, y sin PR abierto vinculado.
3. Orden: bugs de prioridad Alta → Prioridad (Alta, Media, Baja) → Fase más temprana (M0 antes que M1) → número de issue más bajo.
4. Si no hay candidatas, terminá con `RESULTADO: sin-tareas`.

Mové la tarjeta a "En curso" y asignate el issue (`gh issue edit <n> --add-assignee @me`).

## 2. Comprobar el avance

- Leé el issue completo, sus comentarios, su épica padre y sus sub-issues: `gh issue view <n> --comments`.
- Buscá ramas y PRs previos: `gh pr list --search "<n>" --state all`, `git branch -a | grep <n>`.
- Identificá los AC que menciona el issue y buscá en el código y en los tests si ya se cumplen.

## 3. Decidir

- **Ya está hecho:** comentá en el issue qué AC se cumplen y la evidencia (archivo, test, salida del comando). Cerralo, mové la tarjeta a "Hecho" y terminá con `RESULTADO: hecha`.
- **Falta información o hay ambigüedad real** (el issue contradice `SYSTEM.md`, falta un dato de la fuente, hay dos interpretaciones razonables con resultados distintos): comentá en el issue las preguntas, agregá la etiqueta `necesita-humano`, devolvé la tarjeta a "Por hacer" y terminá con `RESULTADO: pregunta`. El comentario empieza con `<!-- tomar-tarea:preguntas -->` y cada pregunta va numerada, se entiende sin leer el resto del issue y trae 2–4 opciones con la que recomendás primero. No preguntes nada que puedas averiguar en el código, los docs o la fuente.
- **Es demasiado grande** (más de ~400 líneas cambiadas o más de un hito): proponé en un comentario cómo dividirla en sub-issues, creálos (cargalos en el Project en "Por hacer"), etiquetá el original `necesita-humano` y terminá con `RESULTADO: dividida`.
- **Hay que implementar:** seguí.

## 4. Implementar

1. Actualizá `main` y creá la rama: `git switch main && git pull --ff-only && git switch -c <n>-<descripcion-corta>`.
2. Escribí primero el test que demuestra cada AC del issue (o reproduce el bug) y verificá que falla.
3. Implementá lo mínimo para que pase. Respetá `docs/SYSTEM.md` §4. Si para avanzar tenés que cambiar una regla de datos, frená (sección 3, ambigüedad).
4. Commits chicos con mensajes en español: `tipo(área): descripción (#n)`.

## 5. Probar

Corré todo lo que aplique y guardá la salida:

- `ruff check .`
- `pytest -q` (con fixture). Si tocaste el pipeline y el original está en `datos/crudo/`, también el pipeline completo y `pytest -q` con datos completos.
- Si tocaste `app/`: build, tests de Playwright y axe.

Si algo falla, corregí la causa real (no desactives tests ni bajes umbrales). Máximo **3 intentos** por falla. Si sigue fallando: abrí el PR como borrador con la salida del error, etiquetá el issue `necesita-humano` y terminá con `RESULTADO: error`.

## 6. Abrir el PR

`git push -u origin <rama>` y `gh pr create` con:

- Título: igual al issue.
- Cuerpo: `Closes #<n>`; qué cambió y por qué; tabla de AC cumplidos con la evidencia de cada uno (test o comando + resultado); qué quedó fuera de alcance.

Mové la tarjeta a "En revisión".

## 7. Validar y mergear

1. **Revisión independiente:** pedile al subagente `revisor` que revise el diff del PR contra el issue, los AC y `docs/SYSTEM.md`. Corregí todo hallazgo **bloqueante** y volvé a pedir revisión (máximo 2 rondas). Los hallazgos no bloqueantes van como comentario en el PR.
2. **CI:** esperá a que terminen los checks: `gh pr checks <pr> --watch`.
3. **Mergeá solo si se cumple TODO esto:**
   - todos los checks de CI en verde;
   - el revisor no tiene hallazgos bloqueantes;
   - cada AC del issue tiene evidencia en el cuerpo del PR;
   - el PR **no** modifica: `docs/SYSTEM.md` §4, `.github/workflows/`, `.claude/`, datos publicados o borrados de datos, ni formatos de id de territorio;
   - el diff tiene menos de ~400 líneas (sin contar fixtures y archivos generados).

   Entonces: `gh pr merge <pr> --squash --delete-branch`. Mové la tarjeta a "Hecho". Si el issue era el último sub-issue abierto de su épica, comentalo en la épica (no la cierres).
4. **Si alguna condición falla:** dejá el PR abierto, comentá cuál condición falló, etiquetá `necesita-humano` y terminá con `RESULTADO: revision` (si solo falta la mirada del mantenedor, p. ej. zona protegida o diff grande) o `RESULTADO: error` (CI rojo o hallazgos bloqueantes sin resolver).

## Prohibido siempre

- Pushear directo a `main`, `git push --force`, `gh pr merge --admin`, saltear hooks (`--no-verify`).
- Borrar ramas ajenas, issues, releases o datos de `datos/crudo/`.
- Cambiar umbrales de tests, permisos, workflows o esta skill para poder mergear.
- Tomar más de una tarea por ejecución.

## Reporte final

Terminá siempre con un resumen corto: issue, decisión, PR, AC cumplidos y, si frenaste, qué necesitás del mantenedor (si son preguntas, copialas tal cual con sus opciones).

La **última línea** es siempre una sola, con este formato exacto (la lee `/trabajar`):

```
RESULTADO: <tipo> issue=#<n> pr=#<m>
```

| `<tipo>` | Cuándo |
|---|---|
| `mergeada` | El PR se mergeó. |
| `hecha` | Ya estaba hecha; se cerró con evidencia. |
| `dividida` | Se dividió en sub-issues (el original queda con `necesita-humano`). |
| `pregunta` | Hay preguntas para el mantenedor. |
| `revision` | El PR está listo pero espera la mirada del mantenedor. |
| `error` | No se pudo terminar por una falla técnica. |
| `sin-tareas` | No hay tareas disponibles (sin `issue` ni `pr`). |

Usá `pr=-` o `issue=-` cuando no corresponda.
