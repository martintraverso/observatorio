# Observatorio Uruguay — Acceptance Criteria: Visual Quality (M10)

Source: visual review of https://martintraverso.github.io/observatorio/ on 2026-11-19, at 1440×900, 1024×768, 768×1024 and 390×844, in Chrome. Each finding (V-xx) is listed with the criteria that close it. IDs `AC-V*` follow the same rules as `ACCEPTANCE_CRITERIA.md`: **[auto]** = automated test (Playwright), **[manual]** = checked by hand with a screenshot in the PR.

**Viewports used by every [auto] criterion below:** 1440×900, 1024×768, 768×1024, 390×844 (the "four viewports").

---

## 1. Findings

Severity: **A** = broken or misleading, **B** = clearly wrong/awkward, **C** = polish.

### Map (`/`)

| ID | Sev. | Finding | Where |
|---|---|---|---|
| V-01 | A | **"Nivel territorial" selector is broken.** It is a CSS grid fixed at 3 columns, but there are 4 options, so "Segmento" sits alone on a second row. Labels have no horizontal padding ("Departamento" touches both edges), "Municipio (Montevideo)" wraps onto two lines, and the selected option is a square block inside a rounded container. | all four viewports |
| V-02 | B | The left panel scrolls inside itself; at 900 px height the legend is below the fold. Switching level makes that scrollbar appear/disappear, the panel width changes and the topic pills re-flow (layout jump). | 1440, 1024 |
| V-03 | B | The map area is blank for ~3–4 s on load with no loading indicator. | desktop |
| V-04 | A | Changing level does not reframe the map. "Municipio (Montevideo)" shows the whole country with Montevideo as a tiny grey shape; "Segmento" shows empty outlines and only says "Acercá el mapa para ver los segmentos". | desktop |
| V-05 | A | The selection survives a level change: with level = Municipio or Segmento, the side panel still shows Tacuarembó (a department) and its department values. | desktop |
| V-06 | B | The availability notice contradicts itself: "«Personas» no se publica por municipio (Montevideo). El nivel más detallado con datos es segmento." (segment is finer than municipality). It should list the levels that do have data. | desktop |
| V-07 | B | Empty right panel ("Tocá un territorio…") permanently takes 330 px (410 px at 1024), leaving the map ~480 px wide at 1024. | 1440, 1024 |
| V-08 | B | Side panel copy: "Total del país: esta fuente no publica un total nacional, y el observatorio no suma territorios para calcularlo." reads like an internal note; the source line is repeated twice; "Ver ficha completa" and "Descargar CSV" have different widths. | desktop |
| V-09 | B | Montevideo, the most populated department, is almost invisible at country zoom. | desktop |
| V-10 | A | Tablet and mobile: the static map preview is uncoloured grey while the legend below shows colour classes; the map starts below the fold (≈ 555 px at 768, ≈ 410 px at 390). The header takes three rows (~210 px) on mobile. | 768, 390 |
| V-11 | C | Mobile topic chips: visible horizontal scrollbar, "Trabajo" cut, no affordance that more chips exist. | 390 |
| V-12 | C | Search placeholder truncated ("…o códigc"). | 1024, 390 |
| V-13 | C | Legend source repeats the year: "Unidades geoestadísticas Censo 2023 · 2023". | all |

### Fichas (`/territorio/...`)

| ID | Sev. | Finding | Where |
|---|---|---|---|
| V-14 | A | "Fuentes de esta ficha" lists **every capture** (~57 monthly ECH reports), each repeating the full license paragraph. The Tacuarembó ficha is **13,586 px** tall on desktop and **44,251 px** on mobile. | all |
| V-15 | A | Internal maintainer notes are shown publicly: "Decisión del mantenedor (2026-11-17): se deja asentado que no hay licencia publicada…". | fichas |
| V-16 | B | Labor chart: native unstyled `<select>`; y-axis ticks are not round numbers (52,2 · 58,9 · 65,7); x-axis only labels first and last period; inconsistent decimals ("60 %" vs "país: 64,1 %"); legend text "(lo publica el INE desde Trimestre móvil dic 2024–feb 2025)" has wrong casing and is hard to read. | desktop |
| V-17 | B | Orange "warning" style is used for purely informative content (sum-of-sections explanation, INE caveats, "Todavía no hay fuentes cargadas"), so real warnings do not stand out. | all |
| V-18 | C | INE caveats box: 8 bullets always expanded. | fichas with ECH |
| V-19 | A | Segment ficha says "Trabajo e ingresos: Todavía no hay fuentes cargadas para este tema" although labor data exists for its department (San José). | segmento, seccion, localidad, barrio, ccz |
| V-20 | B | Mobile ficha: KPI "15.973 km²" wraps; indicator tables scroll horizontally and hide the Fuente column; section nav shows a scrollbar. | 390 |
| V-21 | C | Segment ficha locator only draws a ring at country scale; no close-up of the segment (designed). | segmento |
| V-22 | C | KPI cards "Superficie" and "Localidades" have no source; "Densidad" (designed) is missing. | fichas |

### Fuentes, Datos, layout

| ID | Sev. | Finding | Where |
|---|---|---|---|
| V-23 | B | ECH row in `/fuentes` says "Nivel más detallado: Municipio (Montevideo)" — misleading; it is department-level nationwide, municipality only in Montevideo. | /fuentes |
| V-24 | B | Global footer cites only "INE, Unidades geoestadísticas Censo 2023" (not ECH); on short pages the footer is not at the bottom (grey band below). | /fuentes, all |
| V-25 | B | `/datos`: license box only covers the census geography, not ECH; descriptions show internal level codes ("pais", "seccion", "barrio_mvd"); one long flat list of files. | /datos |

---

## 2. Acceptance criteria

### Controls and layout

- **AC-V1** [auto] *(V-01)* The "Nivel territorial" control shows every available level with no label overflowing its box (`scrollWidth ≤ clientWidth`), no label on more than one line, all options the same height, and no option alone on a row (either all options on one row or a vertical list). Checked at the four viewports and with 3, 4 and 5 levels.
- **AC-V2** [manual] *(V-01)* The level label for municipalities is "Municipio" with the helper text "Solo Montevideo"; the selected state follows the container radius.
- **AC-V3** [auto] *(V-02)* Changing tema, indicador or nivel does not change the width of the left panel or the position of any control above the one clicked (layout shift of the panel = 0). The panel reserves its scrollbar space (`scrollbar-gutter: stable`) or does not scroll at 1440×900.
- **AC-V4** [auto] *(V-02)* At 1440×900 the legend is fully visible without scrolling (e.g. as a map overlay).
- **AC-V5** [auto] No text in buttons, pills, tabs, KPI values or table headers overflows or is clipped, on every route, at the four viewports (generic overflow detector over `button, a, label, th, [role=tab], .kpi`).

### Map behaviour

- **AC-V6** [auto] *(V-03)* A loading state is visible in the map area within 300 ms of navigation and disappears when the first layer is drawn.
- **AC-V7** [auto] *(V-04)* Selecting level "Municipio" fits the map to Montevideo. Selecting "Sección" or "Segmento" fits the map to the selected department if there is one; otherwise segments are drawn as soon as the user zooms in, and the notice offers "Elegí un departamento" with the department list.
- **AC-V8** [auto] *(V-05)* After a level change, the side panel never shows a territory of a different level than the one selected: the selection is cleared, or replaced by the parent/child that contains the previous selection (documented rule).
- **AC-V9** [auto] *(V-06)* The availability notice names the chosen level and lists the levels where the indicator exists, ordered from finest to coarsest, each as a button: "«Personas» no se publica por municipio. Disponible por: segmento · sección · departamento."
- **AC-V10** [auto] *(V-07)* With nothing selected, the map takes at least 70 % of the content width at 1024 and 1440 (empty side panel collapsed or replaced by a compact hint over the map).
- **AC-V11** [manual] *(V-08)* The side panel shows the source once; no sentence describes internal rules; when there is no national total it shows nothing (or "Total del país: no publicado por la fuente" in one short line). Action buttons have equal width.
- **AC-V12** [manual] *(V-09)* Territories smaller than 20×20 px at the current zoom (e.g. Montevideo at country zoom) are findable: a ring/marker on the map or an inset, and they are listed in search.
- **AC-V13** [auto] *(V-10)* At 768 and 390 the map preview uses the same colours as the legend (choropleth image or small static render), and the top of the map is visible within the first 844 px at 390 (controls collapsed into a compact bar or bottom sheet as in the design).
- **AC-V14** [auto] *(V-10)* The mobile header is at most 2 rows (≤ 120 px).
- **AC-V15** [manual] *(V-11)* Mobile topic chips show no scrollbar and indicate more content (edge fade or partial chip plus a "más" affordance).
- **AC-V16** [manual] *(V-12)* The search placeholder is never truncated (shorter text at narrow widths, e.g. "Buscar territorio o código").
- **AC-V17** [auto] *(V-13)* No source/period label repeats the same year twice.

### Fichas

- **AC-V18** [auto] *(V-14)* "Fuentes de esta ficha" shows **one entry per source** (name, organismo, license once, last capture, link to `/fuentes/<id>`), with the capture list collapsed behind "Ver los N archivos". The Tacuarembó ficha is ≤ 6,000 px tall at 1440 and ≤ 15,000 px at 390 with all sections collapsed by default.
- **AC-V19** [auto] *(V-15)* No rendered page contains maintainer-internal text (test for strings such as "Decisión del mantenedor", "se deja asentado", "TODO", "FIXME"). Internal notes stay in `fuentes/*.yml` under a field the app does not render (e.g. `notas_internas`).
- **AC-V20** [auto] *(V-16)* Charts use round tick values (1, 2, 2.5, 5 × 10ⁿ), at least 4 x-axis labels on desktop, the same number of decimals for the territory and the national value, and a styled select consistent with the rest of the UI.
- **AC-V21** [manual] *(V-16)* The national series legend reads "Total del país (INE, desde dic 2024–feb 2025)".
- **AC-V22** [manual] *(V-17)* Three message styles exist and are used consistently: **info** (neutral/blue: explanations, caveats, "no data yet"), **warning** (orange: data the user may misread, e.g. estimates), **error**. The sum-of-sections note and INE caveats use info.
- **AC-V23** [manual] *(V-18)* INE caveats show a 1–2 line summary with "Ver todas las advertencias" expanding the full list.
- **AC-V24** [auto] *(V-19)* When a topic has no data at the ficha's level but has data at a containing level, the ficha says so and links there: "Trabajo: se publica por departamento → ver San José". "Todavía no hay fuentes cargadas" appears only when no level has data.
- **AC-V25** [auto] *(V-20)* At 390: KPI values do not wrap (font scales down or units go on their own line by design), indicator tables become stacked rows with no horizontal scroll, and in-page section navigation has no visible scrollbar.
- **AC-V26** [manual] *(V-21)* Segment, section and locality fichas show a close-up locator (the unit and its neighbours) besides the country locator.
- **AC-V27** [manual] *(V-22)* Every KPI shows its source on hover/focus or in a footnote; department fichas include "Densidad" computed in the pipeline and marked as derived.

### Fuentes, Datos, layout

- **AC-V28** [manual] *(V-23)* The finest-level column can hold several values and says "Departamento · Municipio (solo Montevideo)" for ECH.
- **AC-V29** [auto] *(V-24)* The footer lists every active source (generated from `fuentes.json`) and sits at the bottom of the viewport on short pages.
- **AC-V30** [manual] *(V-25)* `/datos` shows the license of every active source, uses human level names ("País", "Sección censal", "Barrio de Montevideo"), and groups territory files by level with one row per level and a column per format.

### Regression safety

- **AC-V31** [auto] Visual regression: Playwright `toHaveScreenshot` baselines for Mapa (level departamento, with and without selection; level municipio; level segmento), Ficha departamento, Ficha segmento, Fuentes and Datos at the four viewports. Baselines are updated only in PRs labelled `visual`, with before/after images attached.
- **AC-V32** [auto] Existing criteria AC-G4 (no horizontal scroll), AC-G5 (axe), AC-G6 (Lighthouse ≥ 80) and AC-M1…M6 still pass.
