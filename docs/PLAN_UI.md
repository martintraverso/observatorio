# Observatorio Uruguay — Plan M10: Visual quality

Read `docs/ACCEPTANCE_CRITERIA_UI.md` first: it has the findings (V-01…V-25, from the 2026-11-19 visual review of the live site) and the criteria (AC-V1…AC-V32). This plan orders the work so the test harness comes first and the most visible problems are fixed next. One story per PR; list the AC-V IDs in each PR and attach before/after screenshots at the four viewports (1440×900, 1024×768, 768×1024, 390×844).

GitHub: épica "M10 — Pulido visual", milestone M10, label `app` (+ `visual` on PRs that update screenshot baselines). Stories are compatible with `/tomar-tarea`; PRs that update baselines need the maintainer's look before merge (add `visual` to the protected-areas list in the skill's section 7, or keep the diff check: baseline PNGs count as generated files).

Code pointers found during the review (verify before editing): the level selector is a `<fieldset>` with a `.segmentado` div of radio `<label>`s (Svelte); fichas use `section.tarjeta.seccion` and `ul.fuentes`; the main wrapper is `main.contenedor`.

---

## M10.0 — Visual test harness (do first)

1. Playwright project `visual` running the four viewports against the built site served like GitHub Pages (`scripts/servidor-pages.mjs`).
2. Helper `detectarDesbordes(page)` that fails on clipped/overflowing text in `button, a, label, th, [role=tab], .kpi` and on multi-line segmented options (AC-V5, AC-V1).
3. Helper `sinTextoInterno(page)` that fails on maintainer-internal strings (AC-V19).
4. Screenshot baselines for the routes in AC-V31. Mask the map canvas if tiles make screenshots flaky, but keep panels and legend.
5. Run in CI (Chromium only for screenshots; overflow checks in all three browsers).

Done when: harness runs in CI; it **fails** on today's `main` for AC-V1, AC-V5, AC-V18, AC-V19 (proving it catches the problems); baselines are taken only after those are fixed.

## M10.1 — Level selector and left panel (V-01, V-02, V-13)

1. Replace the fixed 3-column grid with a layout that works for any number of levels: a vertical radio list (recommended for the 280 px panel), or a flex row that switches to a vertical list when options do not fit.
2. Label "Municipio" + helper "Solo Montevideo"; consistent padding; selected state with the container's radius (AC-V2).
3. `scrollbar-gutter: stable` on the panel; move the legend to a map overlay (bottom-left) so nothing important is below the fold (AC-V3, AC-V4).
4. Fix the legend source label (AC-V17).

Done when: AC-V1…V5, AC-V17.

## M10.2 — Map behaviour on level change (V-03…V-07, V-09)

1. Loading state in the map area (AC-V6).
2. On level change: fit bounds (Montevideo for municipio; selected department for sección/segmento); otherwise ask the user to choose a department (AC-V7).
3. Selection rule on level change, documented in code and in `docs/SYSTEM.md` §8: keep the territory if it exists at the new level; if moving finer, keep the parent as the map focus and clear the panel; if moving coarser, select the containing parent (AC-V8).
4. Rewrite the availability notice to list available levels as buttons (AC-V9).
5. Collapse the empty side panel into a hint over the map (AC-V10).
6. Ring/marker for very small territories at low zoom (AC-V12).

Done when: AC-V6…V10, AC-V12.

## M10.3 — Side panel copy (V-08)

Source shown once; drop the internal-rule sentence about national totals; equal-width buttons (AC-V11).

## M10.4 — Mobile and tablet map (V-10…V-12)

1. Two-row header (logo + menu/search icon on row 1, nav on row 2 or in a menu) (AC-V14).
2. Controls in a compact bar that opens a sheet; the map visible above the fold; coloured static preview generated from the same classes as the legend (AC-V13).
3. Topic chips without scrollbar and with an edge fade (AC-V15); short search placeholder (AC-V16).

Done when: AC-V13…V16.

## M10.5 — Ficha length and sources (V-14, V-15) — highest priority after M10.1

1. Group "Fuentes de esta ficha" by source: one entry, license once, last capture date, link to `/fuentes/<id>`; the capture list collapsed (AC-V18).
2. Move maintainer decisions out of rendered license text: add `notas_internas` to `fuentes/*.yml`, never rendered; keep the public license text short (AC-V19). For the ECH, the public text can be: "Licencia: no publicada por el INE. Se cita la fuente según cada cuadro." — confirm wording with the maintainer.
3. Check page heights (AC-V18 limits).

Done when: AC-V18, AC-V19.

## M10.6 — Charts and messages (V-16…V-18)

1. Round ticks, ≥ 4 x labels, same decimals, styled select (AC-V20); legend text (AC-V21).
2. Message component with `info` / `warning` / `error` variants and use it everywhere (AC-V22).
3. Collapsible INE caveats (AC-V23).

## M10.7 — Data at containing levels (V-19)

When a topic has no data at the ficha's level, look up the containing levels (ficha JSON already has the parent chain) and link to the first one with data (AC-V24). Applies to segmento, sección, localidad, barrio, CCZ.

## M10.8 — Mobile ficha (V-20) and locators (V-21, V-22)

1. KPI value sizing, stacked tables, hidden nav scrollbar at 390 (AC-V25).
2. Close-up locator for small units (AC-V26).
3. KPI sources; "Densidad" as a pipeline-derived indicator (AC-V27). Pipeline change → keep AC-T and AC-P tests green.

## M10.9 — Fuentes, Datos, footer (V-23…V-25)

Multi-value finest level (AC-V28); footer from `fuentes.json`, pinned to bottom (AC-V29); `/datos` licenses, human level names, grouped files (AC-V30).

## M10.10 — Baselines and close

Take the screenshot baselines (AC-V31), confirm AC-V32, attach a before/after gallery to the épica, and update `docs/SYSTEM.md` §8 with any design decision taken (selection rule, message styles, mobile layout).

---

## Suggested order and priority

| Order | Story | Priority | Size |
|---|---|---|---|
| 1 | M10.0 Harness | Alta | M |
| 2 | M10.1 Level selector + panel | Alta | S |
| 3 | M10.5 Ficha length + internal notes | Alta | M |
| 4 | M10.2 Map on level change | Alta | M |
| 5 | M10.7 Data at containing levels | Alta | S |
| 6 | M10.4 Mobile/tablet map | Media | L |
| 7 | M10.6 Charts + messages | Media | M |
| 8 | M10.3 Side panel copy | Media | S |
| 9 | M10.8 Mobile ficha + locators | Media | M |
| 10 | M10.9 Fuentes, Datos, footer | Baja | S |
| 11 | M10.10 Baselines and close | Media | S |

## Prompt to load it into GitHub (paste in Claude Code)

```
Lee docs/ACCEPTANCE_CRITERIA_UI.md y docs/PLAN_UI.md. Creá en GitHub, sin duplicar lo que exista:
- milestone "M10 — Pulido visual" y etiqueta "visual";
- épica "M10 — Pulido visual" (etiquetas épica + app), con el resumen de hallazgos V-01…V-25;
- una historia por cada M10.x como sub-issue de la épica, con sus AC-V como checklist (texto copiado del archivo), los hallazgos V-xx que cierra, prioridad y tamaño según la tabla, y "Bloqueada por: M10.0" en todas menos M10.0 (M10.10 bloqueada por todas);
- cargalas en el Project (Estado Por hacer, Fase M10, Prioridad, Tamaño). Si falta la opción M10 en Fase, agregala.
Al final mostrame la tabla de issues creados y lo que no pudiste hacer.
```
