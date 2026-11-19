# Flujo autónomo con Claude Code

Claude Code toma una tarea del GitHub Project, la implementa, la prueba, abre el PR, lo hace revisar y lo mergea sin pedir autorización. Frena y te avisa (etiqueta `necesita-humano`) solo cuando algo no cumple las condiciones.

## Piezas

| Archivo | Para qué |
|---|---|
| `.claude/skills/tomar-tarea/SKILL.md` | El procedimiento de una tarea (`/tomar-tarea`). |
| `.claude/skills/trabajar/SKILL.md` | El bucle (`/trabajar`): tarea tras tarea, frena cuando hay preguntas. |
| `.claude/agents/revisor.md` | Revisor independiente que aprueba o bloquea el PR. |
| `.claude/settings.json` | Permisos: qué puede hacer sin preguntar y qué tiene prohibido. |
| `.claude/proyecto.json` | Dueño y número del GitHub Project. |
| Protección de `main` en GitHub | Hace imposible mergear si CI falla. |

## Puesta en marcha (una vez)

1. **Copiá la carpeta `.claude/`** a la raíz del repo y este archivo a `docs/`. Commit y push.
2. **Completá `.claude/proyecto.json`** con tu usuario y el número del Project (está en la URL: `github.com/users/<usuario>/projects/<numero>`).
3. **Dale a `gh` acceso a Projects:** `gh auth refresh -s project`.
4. **Creá la etiqueta de freno:** `gh label create necesita-humano --color D93F0B --description "Claude frenó: requiere decisión del mantenedor"`.
5. **Protegé `main`** (Settings → Branches → Add rule, o Rulesets):
   - Require a pull request before merging (sin aprobaciones obligatorias, porque trabajás solo).
   - Require status checks to pass → elegí el job de CI (`ci`).
   - Do not allow bypassing the above settings.
   - Block force pushes.
6. **Campos del Project:** que existan Estado (Por hacer / En curso / En revisión / Hecho), Prioridad y Fase, con esos nombres.

## Cómo usarlo

**Una tarea, mirando:**
```bash
claude --permission-mode auto
> /tomar-tarea
```

**Un issue concreto:**
```
> /tomar-tarea 42
```

**Sin supervisión, varias tareas seguidas** (cada una en una sesión limpia):
```bash
for i in 1 2 3; do
  claude -p "/tomar-tarea" --permission-mode auto --output-format text | tee -a registro-claude.log
done
```

Al volver, revisá:
- la vista **Hecho** del Project y los PRs mergeados;
- los issues con etiqueta **`necesita-humano`**: ahí Claude dejó preguntas o un PR esperando tu decisión;
- `registro-claude.log`.

## Trabajar en bucle: `/trabajar`

```bash
claude --permission-mode auto
> /trabajar        # hasta 10 tareas
> /trabajar 25     # hasta 25
```

Cada vuelta corre `/tomar-tarea` y lee cómo terminó (línea `RESULTADO:`):

- **mergeada / hecha / dividida** → sigue con la próxima.
- **revision** (el PR espera tu mirada) → lo anota y sigue con otra tarea.
- **error** → lo anota y sigue; con dos errores seguidos, frena.
- **pregunta** → frena y te pregunta en el chat con opciones. Copia tu respuesta al issue y retoma esa tarea. Si decís "saltear", sigue con otra.
- **sin-tareas** → termina con un reporte.

Si no hay nadie en el chat (por ejemplo `claude -p "/trabajar 20" --permission-mode auto`), deja las preguntas en el issue y termina. Respondé en GitHub, comentando normalmente debajo de las preguntas, y la próxima vez que corras `/trabajar` retoma esa tarea primero.

Consejos:
- Más de ~10 tareas por sesión llenan el contexto; para tandas largas, mejor varias sesiones cortas.
- Claude y vos comentan en GitHub con la misma cuenta. Los comentarios de Claude empiezan con una marca oculta (`<!-- tomar-tarea -->`); los tuyos no necesitan nada especial.

## Cuándo Claude frena en lugar de mergear

- El issue es ambiguo, contradice `docs/SYSTEM.md` o es demasiado grande (propone dividirlo).
- Los tests siguen fallando después de 3 intentos (deja PR borrador con el error).
- El revisor encuentra problemas bloqueantes después de 2 rondas.
- El PR toca zonas protegidas: reglas de datos (`SYSTEM.md` §4), workflows de GitHub, `.claude/`, borrado de datos o formato de ids.
- El diff supera ~400 líneas.

Estas tareas las mergeás vos después de mirarlas. Los hitos M0, M3 y M4 tocan workflows, así que sus PRs siempre van a esperar tu revisión.

## Ajustes

- Para darle más autonomía, sacá condiciones de la sección 7 de la skill. Para darle menos, agregalas.
- `.claude/settings.json` tiene prohibido editar `.claude/`: Claude no puede cambiar sus propias reglas. Esos cambios los hacés vos.
