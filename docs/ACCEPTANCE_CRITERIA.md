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
- **AC-F5** [auto] "Descargar CSV" downloads exactly the values shown on the ficha, with columns `territorio_id, nivel, codigo, nombre, indicador, periodo, periodo_inicio, periodo_fin, tipo_periodo, valor, unidad, es_estimado, fuente, archivo_origen, sha256` (period columns added in F2.2, AC-L27).
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
## K. Labor market — ECH departmental report (F2)
 
Source: INE, *Mercado de trabajo por área geográfica de residencia* (monthly HTML report since February 2022). Only official INE URLs.
 
**Capture**
- **AC-L1** [auto] Each monthly report is a capture: the HTML is saved unchanged under `datos/crudo/ech_mt/<año>/<archivo>.html` (and in release `crudos`), with URL, sha256 and download date in `capturas`.
- **AC-L2** [auto] A report-discovery step lists every report from 2022-02 to the latest published one by walking the official INE listing (`https://www.gub.uy/instituto-nacional-estadistica/tematica/mercado-trabajo-area-geografica-residencia?page=N`) and reading, on each publication page, the link to its HTML. File names and folders change over time, so no URL pattern is assumed (F2.1, #40). It records which months were found and which were not; a missing month is reported, not an error.
- **AC-L3** [auto] If INE publishes a new version of a report (e.g. `v1_1`), it is captured as a new capture; the app uses the latest version and keeps the old one traceable (`vigente = false`).
- **AC-L4** [auto] Re-running with unchanged HTML (same sha256) skips parsing (AC-P8).
**Parsing**
- **AC-L5** [auto] From each report the parser extracts, for the 19 departments and, when the report publishes it, total país: `tasa_actividad`, `tasa_empleo`, `tasa_desempleo` (%), `activos`, `ocupados`, `desocupados` (miles de personas, stored as published; the report calls the last two «empleados» and «desempleados»), `tasa_no_registro` (%); and the same for the 8 Montevideo municipalities (A, B, C, CH, D, E, F, G). «Total Montevideo» rows repeat departamento 01 and are not stored again; a rounding difference of up to 0.1 between them (published by INE in two 2026 reports) is accepted as a warning in the validation report, the department value is kept, and a larger difference fails the run (maintainer decision, #59).
- **AC-L6** [auto] Department names in the report map to INE codes (`Montevideo`→`01`, … `Treinta y Tres`→`19`) regardless of accents, case or spacing; an unknown name fails the run.
- **AC-L7** [auto] Decimal separators are parsed correctly: comma ("7,1" → 7.1) and point, used in some older tables ("14.2" in cuadros 3 and 6 of February 2022); values are numeric; no row is silently dropped (expected row counts per table are asserted).
- **AC-L8** [auto] Golden test on the saved July–September 2026 report: Total país 64.1 / 59.5 / 7.1; Montevideo 65.5 / 60.8 / 7.2; Maldonado 69.1 / 65.3 / 5.5; Treinta y Tres 54.1 / 48.6 / 10.2 (actividad / empleo / desempleo).
- **AC-L9** [auto] Golden tests on at least two more saved reports (the first, February 2022, and one from 2024) so format changes across years are covered. Known differences (F2.1, #40): header names («Tasa de Actividad» / «Actividad», «Total de Activos» / «Activos»), a PET column in cuadro 5 (2022, 2024), and total rows only in recent reports. The parser handles each known format explicitly and fails on an unknown one.
**Periods**
- **AC-L10** [auto] Each observation has `tipo_periodo = trimestre_movil`, `periodo_inicio` = first day of the first month and `periodo_fin` = last day of the last month (report `M_09` of 2026 → 2026-07-01 to 2026-09-30), and label `2026-07/2026-09`.
- **AC-L11** [auto] Phase-0 census observations are migrated to `tipo_periodo = censo` without changing their values (AC-T tests still pass).
**Data quality checks** (run on every report; failures stop the run)
- **AC-L12** [auto] All rates are between 0 and 100; `tasa_empleo ≤ tasa_actividad`.
- **AC-L13** [auto] `activos − ocupados = desocupados` within ±1 thousand (rounding).
- **AC-L14** [auto] `desocupados / activos × 100` equals `tasa_desempleo` within ±0.3 points; a larger difference is a warning in the validation report, not a failure: in small departments (Flores, ~14 thousand active) rounding the thousands to one decimal moves the ratio up to ~0.4 points (maintainer decision, option c, #45).
- **AC-L15** [auto] Each report has exactly 19 departments and 8 municipalities per table, plus exactly one «Total país» row (cuadros 1–3) and one «Total Montevideo» row (cuadros 4–6) when the report's format includes them (in the reports surveyed in F2.1, only the 2026 one does). The expected rows for each known format are asserted.
- **AC-L16** [auto] No labor observation exists for sección, segmento, localidad, barrio or CCZ.
**Territory: Montevideo municipalities**
- **AC-L17** [auto] Level `municipio_mvd` has 8 territories with ids `INE-2023/municipio_mvd/<letra>`, parent departamento 01, geometry = union of their CCZ.
- **AC-L18** [auto] Every CCZ belongs to exactly one municipality (from `NOMMUNICIPIO`), recorded in `correspondencias`; the union of the 8 municipalities equals the union of the 18 CCZ (area difference < 0.1%).
- **AC-L28** [auto] Level `pais` has one territory `INE-2023/pais/UY` (geometry = union of the 19 departments). "Total país" values are stored there only for reports that publish them: never on a department, and never derived by summing departments (SYSTEM.md §4) unless flagged `es_estimado = true`.
- **AC-L19** [manual] The municipality ficha and the sources page state that the boundary was derived by the observatory from INE CCZ.
**Registry, report and automation**
- **AC-L20** [manual] `fuentes/ine_ech_mercado_trabajo_departamental.yml` describes the source, URL pattern, tables, periodicity, known caveats (from the INE report) and license/citation.
- **AC-L21** [auto] `reporte_validacion.md` gains a labor section: months captured/missing, checks, and the latest values per department.
- **AC-L22** [manual] The weekly data workflow captures new monthly reports automatically.
**App (applies once M6/M7 exist)**
- **AC-L23** [manual] Topic "Trabajo" in the map offers the 7 indicators at levels departamento and municipio (Montevideo); choosing another level shows the AC-M2 notice.
- **AC-L24** [manual] The legend and the side panel state the period as "Trimestre móvil jul–set 2026" and show "Fuente: INE, ECH".
- **AC-L25** [manual] Department and municipality fichas show the time series since 2022 (line chart vs. total país), not only the latest value.
- **AC-L26** [manual] The INE caveats are visible next to labor data (precision in small departments, place of residence, seasonality, avoid rankings). The app offers no sorted ranking of departments by a single period's value.
- **AC-L27** [auto] Labor values in CSV downloads keep `periodo_inicio`, `periodo_fin` and `tipo_periodo`.
## L. Future phases (criteria to refine when started)
 
- **AC-X1** Census 2023 microdata indicators at segment level are added without breaking AC-T1…T9.
- **AC-X2** Superseded by section L for the departmental labor report. Other ECH indicators (income, poverty) follow the same rules: published values first, stored only at the levels INE publishes, with the survey period.
- **AC-X3** 2011 geometries are loaded with `version_geo = INE-2011` and linked through the INE 2011–2023 correspondence table.
- **AC-X4** Point sources are stored in `eventos` with original coordinates/address and the assigned segment, locality and department.
- **AC-X5** When census zones are obtained, a `zona` level is added under `segmento` and the segment ficha gains a zone list; no existing URL breaks.
 
