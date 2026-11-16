# Observatorio Uruguay — Acceptance Criteria
 
Each criterion has an ID so `PLAN.md` and pull requests can reference it. A criterion is met only when it is verified by an automated test, a reproducible command, or (for UI) a documented manual check with a screenshot.
 
Legend: **[auto]** = must be covered by an automated test · **[manual]** = checked by hand and noted in the PR.
 
---
 
## A. Data pipeline — general
 
- **AC-P1** [auto] `python pipeline/<script>.py <original>` rebuilds its outputs from scratch with no network access other than reading the original file.
- **AC-P2** [auto] Running the full pipeline twice on the same originals produces identical `observaciones.parquet` content (same rows, same values; `fecha_proceso` may differ).
- **AC-P3** [auto] Every row in `observaciones` has a `captura_id` that exists in `capturas`, and every `captura` has a non-empty `sha256` and `archivo`.
- **AC-P4** [auto] Every `territorio_id` in `observaciones` exists in `territorios`.
- **AC-P5** [auto] No observation is stored for a level where the source does not publish it, unless `es_estimado = true`.
- **AC-P6** [auto] The pipeline exits with a non-zero code when any data-quality check fails, and lists the failing checks on stderr.
- **AC-P7** [auto] `reporte_validacion.md` is regenerated on every run and includes counts per level, every check with OK/FALLA, and the department vs. sum-of-sections comparison.
- **AC-P8** [auto] If the original file's sha256 equals the last processed capture, the source is skipped and the run reports "sin cambios".
- **AC-P9** [manual] Each source has a registry file in `fuentes/` with id, nombre, organismo, página, URL de descarga, formato, licencia, frecuencia, version_geo (if geographic) and notes.
## B. Territories (phase 0 — already passing, must keep passing)
 
- **AC-T1** [auto] Counts per level: 19 departamento, 236 seccion, 4,538 segmento, 652 localidad, 63 barrio_mvd, 18 ccz_mvd, 1 area_especial.
- **AC-T2** [auto] Territory ids are unique and follow `INE-2023/<nivel>/<codigo>`.
- **AC-T3** [auto] All geometries are valid and non-empty.
- **AC-T4** [auto] Every `padre_id` exists; every section and segment code starts with its department code; every segment code starts with its parent section code.
- **AC-T5** [auto] Department `01` is "Montevideo" and `16` is "San José" (accented names).
- **AC-T6** [auto] Sum of segments equals its section for all four phase-0 indicators.
- **AC-T7** [auto] `pob_hombres + pob_mujeres = pob_total` for every territory.
- **AC-T8** [auto] The "LIMITE CONTESTADO" polygon is stored as `area_especial` and has zero observations.
- **AC-T9** [auto] Department `pob_total` values equal the INE `depto_23_pg` values (national sum 3,495,947), not the sum of sections (3,338,018).
## C. Web data files
 
- **AC-W1** [auto] For each level there is a browser-ready geometry file: PMTiles for `segmento` (and optionally all levels); GeoJSON allowed for `departamento`, `seccion`, `localidad`, `barrio_mvd`, `ccz_mvd`.
- **AC-W2** [auto] GeoJSON files are ≤ 2 MB each; coordinates have ≤ 5 decimals; simplified geometries keep shared borders without gaps or overlaps between neighbours (coverage simplification).
- **AC-W3** [auto] A search index `territorios_index.json` lists every territory with id, nivel, codigo, nombre, depto, padre_id and bbox; ≤ 1 MB gzipped.
- **AC-W4** [auto] One JSON per territory with everything its ficha needs (identity, parents, children, observations with source references) or an equivalent queryable file; the app needs no server.
- **AC-W5** [auto] A manifest (`web/manifest.json`) lists every published file with size, sha256 and generation date.
## D. Automation
 
- **AC-A1** [auto] CI runs lint (ruff) and pytest on every push and PR.
- **AC-A2** [manual] The data workflow can be started by hand and runs weekly; it downloads originals from release `crudos`, falls back to the source URL, processes, tests and publishes to release `datos`.
- **AC-A3** [manual] A failed data run is visible (red workflow + notification) and never overwrites the last good release `datos`.
- **AC-A4** [manual] The app is rebuilt and deployed automatically when `datos` changes or `app/` changes on `main`.
## E. App — general
 
- **AC-G1** [manual] All UI text is in Spanish (Uruguay). Numbers use `.` as thousands separator and `,` as decimal separator (`es-UY`).
- **AC-G2** [auto] Every displayed value is accompanied by its source name and period; estimates are visibly marked "estimado".
- **AC-G3** [auto] Every territory has a stable, shareable URL `/territorio/<nivel>/<codigo>`; opening it directly works (static hosting, no server).
- **AC-G4** [manual] Works on current Chrome, Firefox and Safari, desktop and mobile (390 px wide) with no horizontal scrolling except inside tables.
- **AC-G5** [auto] Accessibility: axe-core reports no serious or critical violations on Mapa, Ficha, Fuentes and Datos; all interactive elements are reachable by keyboard; touch targets ≥ 44 px; text contrast ≥ 4.5:1.
- **AC-G6** [auto] Performance: Lighthouse performance ≥ 80 on mobile for the home page; initial JS ≤ 300 KB gzipped (MapLibre excluded); segment geometries load only when zoomed in or requested.
- **AC-G7** [manual] Attribution "Fuente: INE" is visible on every map and in every download.
## F. Search
 
- **AC-S1** [auto] Typing ≥ 2 characters suggests matching departments, localities, barrios and codes; matching ignores accents and case ("paysandu" finds "Paysandú").
- **AC-S2** [auto] Typing a valid INE code (2, 4, 5 or 7 digits) goes to that territory.
- **AC-S3** [manual] Results show the level and parent ("Sección 05 · San José").
## G. Map
 
- **AC-M1** [manual] Shows real INE 2023 boundaries for the chosen level with a choropleth of the chosen indicator, a legend with class breaks and units, and the source.
- **AC-M2** [auto] Choosing an indicator not published at the chosen level shows a notice naming the finest available level; the map does not show invented values.
- **AC-M3** [manual] Clicking a territory selects it: highlight on the map, right panel updates (name, level, code, value, national total, source, other indicators).
- **AC-M4** [manual] The right panel includes a locator mini-map of Uruguay highlighting the selected territory (with a ring for small ones such as Montevideo).
- **AC-M5** [auto] The map state (indicator, level, selected territory) is reflected in the URL and restored when the URL is opened.
- **AC-M6** [manual] On mobile, the panel becomes a bottom sheet and topic selection a horizontal chip row.
## H. Fichas
 
- **AC-F1** [auto] Department, section, segment and locality fichas exist for every territory of those levels.
- **AC-F2** [manual] A ficha shows breadcrumb, name, level, code, locator map, key figures with source, and links to parent and child territories.
- **AC-F3** [manual] A segment ficha shows its own counts and, in "Más datos en los niveles que contienen este territorio", the section and department values with links.
- **AC-F4** [manual] Department fichas explain, where relevant, that the sum of sections does not equal the department total, with the INE reason.
- **AC-F5** [auto] "Descargar CSV" downloads exactly the values shown on the ficha, with columns `territorio_id, nivel, codigo, nombre, indicador, periodo, valor, unidad, es_estimado, fuente, archivo_origen, sha256`.
- **AC-F6** [manual] "Cómo citar" produces a citation including the observatory, the territory, the access date and the original source (INE).
- **AC-F7** [manual] Topics with no data show an explicit "Todavía no hay fuentes cargadas para este tema" notice.
## I. Fuentes
 
- **AC-SRC1** [auto] `/fuentes` lists every registry file in `fuentes/` with organismo, temas, finest level, frequency, last capture and status (activa / en preparación / a relevar).
- **AC-SRC2** [manual] Filters by status, organismo and level work and combine.
- **AC-SRC3** [auto] `/fuentes/<id>` shows the technical sheet, derived indicators, and the full capture history from `capturas` (date, file, sha256, result).
- **AC-SRC4** [manual] License text and contact are shown exactly as in the source's metadata.
## J. Datos (downloads)
 
- **AC-D1** [auto] `/datos` offers full downloads: observations (Parquet and CSV), territories per level (GeoJSON, and GeoParquet with full-resolution geometry), and the DuckDB file.
- **AC-D2** [manual] Each download states size, generation date, license and how to cite.
## K. Future phases (criteria to refine when started)
 
- **AC-X1** Census 2023 microdata indicators at segment level are added without breaking AC-T1…T9.
- **AC-X2** ECH indicators are stored only at department and country level, with survey period and design notes (panel since July 2021).
- **AC-X3** 2011 geometries are loaded with `version_geo = INE-2011` and linked through the INE 2011–2023 correspondence table.
- **AC-X4** Point sources are stored in `eventos` with original coordinates/address and the assigned segment, locality and department.
- **AC-X5** When census zones are obtained, a `zona` level is added under `segmento` and the segment ficha gains a zone list; no existing URL breaks.
 
