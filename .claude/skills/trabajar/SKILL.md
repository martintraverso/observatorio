---
name: trabajar
description: Bucle de trabajo del Observatorio. Ejecuta /tomar-tarea una y otra vez, tarea tras tarea, hasta que no quedan tareas; si una tarea deja preguntas, frena, se las hace al mantenedor y, cuando responde, sigue. Usar cuando el mantenedor invoca /trabajar o pide "trabajá en el proyecto hasta terminar".
argument-hint: "[máximo de tareas, por defecto 10]"
disable-model-invocation: true
---

# Trabajar en bucle

Repetís el procedimiento de `/tomar-tarea` hasta que no quedan tareas, hasta llegar al máximo de la sesión o hasta que una tarea necesita respuestas del mantenedor. Las autorizaciones son las mismas de `/tomar-tarea`, ni una más.

## Antes de empezar

1. Leé `.claude/skills/tomar-tarea/SKILL.md` completo. Es el procedimiento de **cada** vuelta del bucle; esta skill solo decide qué hacer entre una vuelta y la siguiente.
2. Máximo de tareas: `$ARGUMENTS` si es un número; si no, 10.
3. Iniciá el registro de la sesión (en tu memoria de trabajo, y al final en el reporte): por cada vuelta, issue, `RESULTADO`, PR y una línea de resumen.

## Cada vuelta

1. **Punto de partida limpio:** `git switch main && git pull --ff-only` y `git status` sin cambios. Si quedaron cambios sin commitear de una vuelta anterior, no los descartes: frená y avisá (sección "Frenar").
2. **¿Hay preguntas ya respondidas?** Buscá issues abiertos con `necesita-humano` cuyo último comentario `<!-- tomar-tarea:preguntas -->` tenga una respuesta posterior (comentario que no empieza con `<!-- tomar-tarea`):
   `gh issue list --label necesita-humano --state open --json number,title`
   y para cada uno `gh issue view <n> --comments`. Si hay alguno, esta vuelta es ese issue (el de número más bajo).
3. **Ejecutá `/tomar-tarea`** siguiendo su SKILL.md: con el número del paso 2 si lo hubo, o sin número para que elija la próxima tarea.
4. **Leé la línea `RESULTADO:`** con la que terminó y decidí:

| Resultado | Qué hacés |
|---|---|
| `mergeada`, `hecha`, `dividida` | Anotalo y seguí con la próxima vuelta. |
| `revision` | Anotalo (el PR espera al mantenedor) y seguí: `/tomar-tarea` ya no va a elegir esa tarea, y las que dependen de ella quedan bloqueadas. |
| `error` | Anotalo y seguí. Si es el **segundo `error` seguido**, frená: probablemente el problema no es de la tarea (CI caído, entorno roto). |
| `pregunta` | Andá a "Preguntas". |
| `sin-tareas` | Terminá (reporte final). |

5. **Antes de la próxima vuelta:** si llegaste al máximo de tareas, terminá. Si no, empezá la vuelta siguiente sin pedir permiso.

No arrastres detalles de una tarea a la siguiente: cada vuelta vuelve a leer el issue, el código y los docs desde cero.

## Preguntas

1. Leé el comentario `<!-- tomar-tarea:preguntas -->` del issue.
2. Si hay alguien en la conversación, hacé las preguntas con la herramienta de preguntas de opción múltiple (AskUserQuestion): una pregunta por cada pregunta del comentario (máximo 4 por vez; si hay más, en tandas), con sus opciones y la recomendada primero, y en el encabezado el número de issue. Esperá la respuesta.
3. Con la respuesta:
   - Publicala en el issue, tal cual, en un comentario que empiece con `<!-- trabajar:respuestas -->`, numerada igual que las preguntas.
   - Si el mantenedor dijo "saltear", "después" o similar: dejá el issue como está y seguí con la próxima vuelta sin ese issue.
   - Si no: la próxima vuelta es `/tomar-tarea <n>` (va a sacar la etiqueta y retomarlo con las respuestas).
4. Si no hay nadie para responder (sesión sin interfaz, p. ej. `claude -p`, o la herramienta de preguntas no está disponible): no esperes. Dejá las preguntas en el issue y terminá con el reporte final; cuando el mantenedor responda en GitHub y vuelva a correr `/trabajar`, el paso 2 de la vuelta lo retoma.

## Frenar

Frená el bucle (reporte final, sin empezar otra vuelta) si:

- hay cambios sin commitear o una rama a medio hacer que no sabés de qué vuelta son;
- hubo dos `RESULTADO: error` seguidos;
- `/tomar-tarea` terminó sin línea `RESULTADO:` (no adivines el resultado);
- el mantenedor lo pide en la conversación.

## Prohibido

Todo lo prohibido en `/tomar-tarea`, más: cambiar el orden o la prioridad de las tareas del Project, sacar la etiqueta `necesita-humano` de un issue sin respuesta, y responder vos las preguntas de una tarea.

## Reporte final

Tabla con cada vuelta (issue, resultado, PR, resumen de una línea) y, debajo:

- **Esperan tu mirada:** PRs en `revision` (con enlace).
- **Esperan tu respuesta:** issues con preguntas sin responder.
- **Errores:** issues con `error` y la causa en una línea.
- **Siguiente:** la próxima tarea que tomaría `/tomar-tarea`, o "No quedan tareas".

Última línea: `BUCLE: <vueltas> vueltas · <mergeadas> mergeadas · <pendientes> esperan al mantenedor · motivo de fin: <sin-tareas|máximo|pregunta|errores|pedido>`.
