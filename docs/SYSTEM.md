# Observatorio Uruguay — System Description
 
## 1. Purpose
 
Observatorio Uruguay collects public data about what happens in Uruguay's territory, stores it in its own database, and **links every data point to a territory** (department, census section, census segment, locality, Montevideo neighbourhood). A friendly web app lets anyone explore the data on a map, read a profile ("ficha") for each territory, see where every number comes from, and download it.
 
Product language: **Spanish (Uruguay)**. All UI copy is in Spanish. Code identifiers, table and column names are also in Spanish (they already are in phase 0). Keep it that way.
 
## 2. Constraints
 
- **One maintainer.** No servers, no managed database, no paid services. Everything must be rebuildable from scratch with one command.
- **Static-first.** Data pipeline runs in GitHub Actions; outputs are files (Parquet, GeoJSON/PMTiles, JSON); the app is a static site that reads those files.
- **Free hosting** (Cloudflare Pages or GitHub Pages).
- **Traceability over convenience.** Every value shown must point to its source file, download date and checksum.
- The INE website is unreliable for downloads. Original files are kept as assets of a GitHub release named `crudos` and the pipeline reads them from there first. Sources with many originals (`carpeta_original`, e.g. the ECH reports) store each file as `<carpeta>-<sha12><ext>` (`.html` for the ECH reports, `.xlsx` for the income series) plus a versioned capture registry, and are rebuilt only from `crudos` (`scripts/crudos_carpeta.py`). The ECH labour reports are captured by hand and uploaded with `scripts/subir_crudos.sh`; the income series are captured by the weekly data workflow, which uploads new versions to `crudos` before processing (F3.6).
## 3. Territorial model
 
Source: INE, *Unidades geoestadísticas Censo 2023* (zip of GeoPackages, EPSG:4326, scale 1:50,000). License: "El uso es libre, citando como fuente al INE."
 
| `nivel` | Count | Code (`codigo`) | Parent |
|---|---:|---|---|
| `departamento` | 19 | 2 chars, alphabetical, Montevideo = `01` | — |
| `seccion` | 236 | 4 = depto + sección | departamento |
| `segmento` | 4,538 | 7 = sección + segmento | seccion |
| `localidad` | 652 | 5 = depto + localidad (`900` = rural) | departamento |
| `barrio_mvd` | 63 | INE barrio code | departamento 01 |
| `ccz_mvd` | 18 | CCZ number, 2 digits | departamento 01 |
| `municipio_mvd` | 8 | letter: A, B, C, CH, D, E, F, G | departamento 01 (derived in F2.3: union of its CCZ) |
| `pais` | 1 | `UY` | — (derived in F2.3: geometry = union of the 19 departments; for national totals) |
| `area_especial` | 1 | `02-limite-contestado` | departamento 02 |
| `region` | 3 | `interior`, `interior-5000`, `interior-menores` | pais (no geometry; F3.2) |
 
- Territory id: `INE-2023/<nivel>/<codigo>` (e.g. `INE-2023/segmento/1605601`).
- Hierarchy depto → sección → segmento is derivable from the code prefix.
- Segment → locality comes from the INE attribute `CODLOC` (stored in `correspondencias`).
- **Census zones (zona censal, 10-char code) are NOT in the INE package.** The segment is the finest unit available. Anything in the design that says "zona" must be implemented as "segmento" until zones are obtained.
- **Level `region`** (decided by the maintainer on 2026-11-19, F3.2): 3 territories without geometry — `INE-2023/region/interior` ("Interior del país"), `INE-2023/region/interior-5000` ("Interior: localidades de 5.000 o más habitantes"), `INE-2023/region/interior-menores` ("Interior: localidades pequeñas y zonas rurales"); parent `pais/UY`. They are the areas in which INE publishes ECH income series. `geometry` and `area_km2` are NULL; they are never drawn on the map and are skipped by geometry checks and exports, but appear in search, fichas and downloads. Relations in `correspondencias` (relation only, nothing is summed): `interior-5000` and `interior-menores` → `interior`; the 18 departments other than 01 → `interior`; `interior` → `pais`. Montevideo is `departamento/01`; total país is `pais/UY`. Their codes are the observatory's, not INE codes.
- Geometries are versioned (`version_geo`). 2011 geometries will coexist with 2023 ones; INE publishes a 2011–2023 correspondence table.
## 4. Core data rules (non-negotiable)
 
1. **Store every value at the level where the source publishes it. Never aggregate population upward.** INE geolocates part of the administratively-enumerated population only at locality or department level. In 2023: departments sum to 3,495,947 people; sections/segments sum to 3,338,018 (−157,929; between 1.6% and 8.4% per department). Dwellings (viviendas) do match (±3).
2. Downward apportioning (department → smaller unit) is allowed only as an **estimate**, flagged `es_estimado = true`, and shown as such in the UI.
3. Every observation has a `captura_id` → source file name, sha256, processing date.
4. If an indicator does not exist at the level the user selected, the app **says so** and offers the nearest level that has it. It never fabricates or silently substitutes.
5. Raw files are immutable. If the checksum did not change, the source is not reprocessed.
6. The "LIMITE CONTESTADO" polygon has no observations of its own (INE repeats Artigas' counts on it).
7. **(PROPOSAL, F3.9 — pending the maintainer's approval)** Values the source does not publish may be **computed by the observatory from the source's microdata** only when the maintainer approves the indicator, and only with: `es_calculado = true`, a stated method, a margin of error and the sample size, indicators distinct from the published ones, a check that reproduces a published figure, and the label "calculado por el observatorio" wherever they are shown. Microdata whose terms forbid redistribution are never stored in public places.
## 5. Data model (implemented in phase 0)
 
```
territorios(id, nivel, codigo, nombre, depto, padre_id, version_geo, area_km2, codigo_iso, geometry)
observaciones(indicador, territorio_id, periodo, periodo_inicio, periodo_fin, tipo_periodo, valor, es_estimado, captura_id)
indicadores(codigo, nombre, unidad, tema, columna_origen, fuente_id, nota, es_derivado, formula)  -- es_derivado: computed by the observatory from published values (F4.2); formula: how, empty for published values
capturas(id, fuente_id, archivo, sha256, fecha_proceso, url, descargado, vigente)  -- descargado: download date, if recorded; vigente: latest version (F2.5b)
capturas_historial(id, fuente_id, archivo, sha256, fecha_proceso, resultado, detalle)  -- append-only, one row per run
fuentes(id, nombre, organismo, pagina, url_descarga, formato, licencia, frecuencia, estado, contacto,
        version_geo, temas[], nivel_mas_detallado, niveles_publicados[], notas[])  -- from fuentes/*.yml; notas_internas[] stays in the yml, never published (AC-V19)
correspondencias(origen_id, destino_id, tipo, peso, metodo)
VIEW v_observaciones  -- observaciones joined with territorio, indicador and captura
```
 
**Time periods (F2.2, implemented):** survey indicators refer to a 3-month moving quarter, not a year. `observaciones` has `periodo_inicio` (date, first day), `periodo_fin` (date, last day) and `tipo_periodo` (`censo`, `mes`, `trimestre_movil`, `trimestre`, `semestre`, `anio`). `periodo` stays as a human label (e.g. `2026-07/2026-09`). Phase-0 census rows are `tipo_periodo = censo`, `periodo_inicio = periodo_fin = 2023-01-01` with label `2023`.
 
**Level added in F2.3:** `municipio_mvd` (8 Montevideo municipalities). INE does not publish its geometry in the 2023 package, but `ccz_mvd_23_pg` has the attribute `NOMMUNICIPIO`; the geometry is derived by dissolving CCZ by municipality and recorded in `correspondencias` (ccz → municipio, `metodo = "disolución de CCZ por NOMMUNICIPIO"`). Each departamento is recorded as `pertenece_a` the `pais` territory (a relation only: no values are summed). Derived levels get `area_km2` measured on their geometry.
 
**Level added in F3.2:** `region` (3 territories, see §3), the only level whose `geometry` and `area_km2` are NULL. The web build skips it in GeoJSON, PMTiles and per-level downloads; in `territorios_index.json` and fichas it has `bbox = null`, and the app shows its ficha without a map.

**Income rules (F3):** values stored exactly as published (full precision); the price base is part of the indicator (current pesos and pesos of January 2005 are different indicators; the observatory never deflates or converts); quarterly rows are `tipo_periodo = trimestre`, yearly totals `anio`; a changed file is a new capture whose values replace earlier ones for the same period (`vigente`), with a change summary in the report.

**Education rules (F4, MEC *Anuario Estadístico de Educación*; plan `docs/PLAN_educacion.md`, criteria `docs/ACCEPTANCE_CRITERIA_educacion.md`):**
- *Territories.* Row "TOTAL" → `pais/UY`; "MONTEVIDEO" → `departamento/01`; each of the 18 department names → `departamento/<código INE>`, matched by name without accents or case (an unknown name in a by-department table fails the run); "RESTO DEL PAÍS" → `region/interior` (the F3.2 level). Nothing below departamento is published and nothing is estimated downward. "RESTO DEL PAÍS" rows are loaded only if `region/interior` exists and the row equals TOTAL − MONTEVIDEO; otherwise they are skipped and reported.
- *Period.* Each file covers one school year (March–December): `tipo_periodo = anio`, `periodo_inicio` YYYY-01-01, `periodo_fin` YYYY-12-31, label `YYYY`. The year comes from the table title and must equal the file's year.
- *One year per file.* Each table holds a single year; series are built by loading one anuario per year. Each anuario is its own capture: a revised table in a later edition does not overwrite an earlier year unless that year is republished in a new version of the same file. **Exception (D4):** values the footer declares to be from an earlier year are stored with that real year, with the capture of the anuario that publishes them and the footer note. A value that is already loaded (that year's own anuario publishes it) is not loaded again; a difference is a warning. Indicators keep the concepts of the latest anuario's tables (D6).
- *Counts as published.* One indicator per measure and breakdown (e.g. `edu_…_publica`, `edu_…_publica_mujer`), in units "estudiantes", "establecimientos", "docentes" or "grupos". **A breakdown whose meaning changes between years is a different indicator**, never the same one (II-2.2.1: the sex totals cover all administrations in 2023 but only public schools in 2024).
- *Table types (decision D1).* A: rows by department → `pais/UY`, `departamento/*`, `region/interior`. B: national totals by category → `pais/UY`, the category is part of the indicator. C: rows by institution or campus → a department only where the row names it, otherwise `pais/UY`. An institution is never a territory.
- *Derived rates (decision D2).* Promotion rate, % private enrolment and % insufficient attendance are computed by the observatory from the stored counts, only when numerator and denominator come from the same table, year and scope. Each is its own indicator with `es_derivado = true`, its `formula`, and the label "calculado por el observatorio a partir de MEC". They are never mixed with INE percentages.
- *Notes travel with the value.* Each table's "Fuente:" and "Nota:" rows are kept in the capture metadata, linked to the table code, and shown in the app (e.g. "Pública no incluye JICI"; rendimiento counts end-of-year results, not initial enrolment; Montevideo has no rural public primary).

Planned additions: `eventos(id, dataset_id, fecha, geometry, territorio_id, atributos_json, captura_id)` for point data.

`resultado` in `capturas_historial`: `nuevo`, `reprocesado` (same original, `--forzar`), `sin cambios` (same sha256 as the last processed capture: not reprocessed) or `error`. Shared pipeline code lives in `pipeline/comun/` (M1). Each source writes its own `observaciones`, `capturas` and `indicadores` to `datos/salida/fuentes/<fuente_id>/`; `comun.salida.combinar` builds the shared tables and the DuckDB file from them and fails if they do not fit (unknown territory, indicator or capture; the same indicator, territory and period twice; indicators or captures repeated across sources; a source folder not in the registry). If a source has no folder (in Actions only the shared tables are downloaded), it is rebuilt from the shared tables (F2.5c).
 
Phase 0 indicators (Censo 2023, every level): `pob_total`, `pob_hombres`, `pob_mujeres`, `viviendas_total`.
 
## 6. Architecture
 
```
fuentes/*.yml            source registry (one file per dataset)
        │
pipeline/*.py            one script per source: read original → normalize → georeference
        │                (reads original from release "crudos", falls back to source URL)
datos/salida/            observatorio.duckdb + *.parquet + web/ (GeoJSON, later PMTiles, JSON)
        │
GitHub Actions           manual + weekly; pipeline/correr.py, pytest, publishes release "datos-<date>" (latest)
        │
app/                     static site (SvelteKit, M4) reading the published files
        │
GitHub Pages (chosen by the maintainer, 2026-11-17)
```
 
Stack: Python 3.12, geopandas, pyogrio, shapely ≥ 2.1, pandas, pyarrow, duckdb, pytest. App: to be decided in the plan (recommended: SvelteKit with `adapter-static`, MapLibre GL JS, PMTiles).
 
## 7. Current state (phase 0, done)
 
- `pipeline/territorios_2023.py` loads all 7 levels and 22,104 observations in ~15 s; writes Parquet, DuckDB, simplified GeoJSON per level (`web/`), and `reporte_validacion.md`.
- 9 data-quality checks pass; 7 pytest tests pass.
- `.github/workflows/fase0.yml` runs it on demand and weekly (replaced by `datos.yml` in M3).
- Web GeoJSON sizes: departamento 0.4 MB, seccion 1.7 MB, segmento 10.2 MB, localidad 0.8 MB, barrio 0.2 MB, ccz 0.1 MB. Segments are too heavy for the browser as GeoJSON → PMTiles needed.
## 8. The app (designed, not built)
 
Design canvas: https://claude.ai/artifact/Ptk7RiGZ5N6KerdktAGkaz (may not be accessible from Claude Code; this section is the source of truth).
 
Visual system: Inter (body) + Space Grotesk (headings); ground `#F6F7F5`, cards `#FFFFFF` with `#DDE1E5` borders, radius 10–16 px; sequential blue ramp `#EAF1F8 #C3D7EC #8DB4DB #4F86C0 #1F5A96`; selection accent orange `#E07A1F`; primary button `#1F4E8C`. Touch targets ≥ 44 px. Text contrast ≥ 4.5:1.
 
Global header: logo + "Observatorio Uruguay", nav (Mapa · Fichas · Datos · Fuentes), search box "Buscar departamento, localidad o código INE" (shorter placeholder "Buscar territorio o código" when the long one does not fit). On mobile (≤ 640 px) the header has two rows: logo (name for screen readers only) + nav; search.

Global footer: every active source (from `fuentes.json`) with a link to its page; it sits at the bottom on short pages.

Messages (M10, AC-V22): three styles used consistently — **info** (blue: explanations, source caveats, "todavía no hay…"), **warning** (orange: data that can be misread, e.g. estimates), **error** (red: something failed or does not exist).
 
**Mapa** (`/`)
- Left panel: Tema pills (Población, Vivienda, Hogares, Trabajo, Ingresos, Educación) → Indicador list (each shows source and the finest level available) → Nivel territorial (vertical list, from the level catalogue: Departamento | Municipio «Solo Montevideo» | Sección | Barrio «Solo Montevideo» | Segmento; only the levels of the **selected indicator** that have values in at least 2 territories (`niveles_mapa`, #204) and can be drawn; one level shows as the text «Nivel: Departamento», none hides the selector — M11.4) → Período.
- **Level catalogue (M11.1):** `pipeline/web.py` writes `niveles.json`, a separate file (`indicadores.json` keeps its shape: one list of indicators, each with the `niveles` where it has observations, AC-N2). Each entry has `id`, `etiqueta`, `ayuda`, `orden` (coarse to fine, D2), `dibujable`, `capa` (has a PMTiles layer even if not offered, e.g. localidad and CCZ: the map outlines there what the search selects), `minzoom`, `ambito` (`pais` | `montevideo`) and `dentro_de` (the levels that contain each of its territories entirely; when the indicator changes and the current level is not offered, the map goes to the nearest of these that is, else to the coarsest offered — AC-N7, maintainer's answer in #202). `dibujable` means the level goes on the map (decision D1, #200: departamento, municipio, sección, barrio, segmento; seccional with F5) **and** has a PMTiles layer. Localidad and CCZ have a layer but are not offered (D1); país and región never are (AC-N3). Since M11.2–M11.3 the app reads it: layers, labels, minimum zoom, selection outlines, and framing (AC-V7: `ambito = montevideo` → Montevideo; a level not inside a department → the country; otherwise the selected department), and a URL `nivel` that the indicator does not offer opens with the AC-N7 rule (AC-N8).
- Changing the level reframes the map (Montevideo for Municipio; the selected department for Sección/Segmento) and applies the **selection rule** (AC-V8): the side panel never shows a territory of another level. The selection is kept if it belongs to the new level; if one of its parents does (going coarser), that parent is selected; otherwise (going finer) the panel is cleared and the map stays framed on the department.
- Center: choropleth map with real INE boundaries, legend as an overlay (bottom-left; map fits leave its space), zoom controls, attribution "Límites: INE, unidades geoestadísticas 2023". A "Cargando el mapa…" state until the first draw. Departments smaller than 48 px on screen (Montevideo at country scale) get a ring that selects them. With nothing selected the right panel is not shown and a hint sits over the map.
- Since M11.4 the map never shows «no se publica por…» (AC-N9; the AC-M2/AC-V9 notice applies to fichas only). Changing topic or indicator keeps the level if offered, otherwise moves to the nearest offered level that contains it, else the coarsest (AC-N7), and announces it in a polite live region. An indicator with no level on the map shows its own notice: by region (Ingresos) with the AC-I20 comparison, or «se publica solo para todo el país».
- Right panel: selected territory name, level and INE code; **locator mini-map** of Uruguay with the territory highlighted (circle around very small ones like Montevideo); main value with unit, national total, source + methodology link; 3 other indicators; buttons "Ver ficha completa" and "Descargar CSV".
- Mobile (≤ 900 px): a compact bar summarises the choice ("Personas · Departamento · 2023 · Cambiar") and opens the controls in a bottom sheet, so the map starts within the first screen; before tapping, the map preview is coloured with the legend classes; topic chips scroll without a visible scrollbar and fade at the edge; bottom sheet with the selected territory.
**Ficha de departamento** (`/territorio/<nivel>/<codigo>`)
- Breadcrumb; name, level, code; KPIs (personas, viviendas, superficie, localidades, and for departments "Densidad", **computed by the app** from the census population and the INE geometry area, marked "calculada", never stored as an observation — #111) with a footnote naming the source of each; locator map; actions: Descargar CSV, Copiar enlace, Cómo citar.
- Section nav: Población · Vivienda y hogares · Trabajo e ingresos · Educación · Dentro del departamento · Fuentes.
- Indicator cards compare the territory vs. national total; population pyramid; annual series chart for survey indicators.
- "Dentro del departamento": table of child units (secciones / localidades / segmentos) with counts and "Ver en el mapa".
- Empty topics show an explicit "no sources loaded yet" notice instead of blank space; if a containing level has data for that topic, the ficha says so and links there ("Trabajo: se publica por departamento → ver San José").
- Series charts: round y ticks, ≥ 4 x labels, same decimals for territory and country. Source caveats (e.g. INE for the ECH): a visible summary naming every topic and the full list folded ("Ver todas las advertencias").
- Mobile: KPI values on one line, indicator tables as stacked rows, section nav without a visible scrollbar.
- "Fuentes de esta ficha": one entry per source (name linked to `/fuentes/<id>`, license once, last capture) with its files folded behind "Ver los N archivos"; citation text. Maintainer notes stay in `notas_internas` and are never shown.
**Ficha de segmento** (designed as "zona"; implement as segmento)
- Breadcrumb Uruguay › Depto › Sección › Segmento; code chips; counts (personas, viviendas) with share of section and department; locator map + close-up of the unit among neighbours (segment, section and locality fichas; for localities the context is the surrounding sections; large rural segments, below the PMTiles segment zoom, are shown as their bounding box among sections).
- "Más datos en los niveles que contienen este territorio": cards for sección and departamento with their indicators and links.
- "Hechos registrados" placeholder for future point sources; "En censos anteriores" placeholder for 2011 correspondence.
**Fuentes** (`/fuentes`) — catalog: summary counts (activas, en preparación, a relevar, última revisión), filters (search, organismo, nivel, estado), table (fuente, temas, nivel más detallado, frecuencia, última captura, estado badge), and a 4-step "Cómo trabajamos con cada fuente" explainer.
 
**Detalle de fuente** (`/fuentes/<id>`) — description, ficha técnica, indicators derived, capture history (date, file, sha256, result: nuevo / sin cambios / error), notes/warnings, "hasta dónde llega en el territorio", related tools, "Reportar un problema".
 
**Datos** (`/datos`) — bulk downloads: observations, territories grouped by level (one row per level with readable names, one column per format: GeoParquet, GeoJSON), full database; the license of every active source and a citation naming them.

The "Nivel más detallado" of a source (in `/fuentes`) names the finest nationwide level and, if finer, the Montevideo-only one ("Departamento · Municipio (solo Montevideo)").

Visual regression (AC-V31): Playwright screenshot baselines of the main pages at 1440, 1024, 768 and 390 px, taken on the CI runner with the fixture; updated only in PRs labelled `visual`.
 
## 9. Known sources (see `fuentes/` and project notes)
 
Active: INE unidades geoestadísticas 2023.
 
**Labor market (F2, next):** INE report *"Mercado de trabajo por área geográfica de residencia"*, monthly since February 2022. Official estimates for the 19 departments, the 8 Montevideo municipalities and, in recent reports, total país, as 3-month moving averages. Tables: activity, employment and unemployment rates (%); active, employed and unemployed (thousands); non-registration in social security (%). Published only as an HTML page (no spreadsheet): the pipeline must save each page and parse its tables. INE publishes no confidence intervals and warns: smaller departments are less precise; figures are by place of residence; seasonality (e.g. Maldonado); avoid single-period rankings. Example HTML: `https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/HTML/ECH/Mercado%20de%20trabajo%20por%20%C3%A1rea%20geogr%C3%A1fica/2026/Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.html` (July–September 2026). Country/Montevideo/Interior long series exist as xlsx (`series-historicas-actividad-empleo-desempleo`), without departments. ECH microdata are used only for indicators INE does not publish, labelled "calculado por el observatorio". **Only official INE sites are valid sources.**
 
**Income (F3, `fuentes/ine_ech_ingresos_series.yml`):** INE *Series históricas ECH Ingresos de las personas y los hogares* (xlsx, quarterly since 2016) for total país, Montevideo and the Interior (total, localities of 5,000 or more, small localities and rural areas): mean household and per-capita income, with and without aguinaldo and valor locativo, at current prices and at January 2005 prices. Since 2025 INE uses the *ingreso disponible ajustado* (YDA); the 2016– series were recomputed with it (F3.1). Plan: `docs/PLAN_ingresos.md`; criteria: `docs/ACCEPTANCE_CRITERIA_ingresos.md`.

**No department income:** INE publishes no current official income or poverty figure by department (its 2025 poverty report has tables only by region; the department map is an image). MIDES publishes department series to 2023, but its income series looks mislabelled (values not consistent with current pesos) and its poverty series uses INE's 2006 method. Department income, if ever added, must be computed from ECH microdata and labelled "calculado por el observatorio" (F3.9, needs approval).

**Education (F4, registry `fuentes/mec_anuario_educacion.yml` from F4.1, en preparación):** MEC *Anuario Estadístico de Educación* (División de Investigación y Estadística, Dirección Nacional de Educación), one xlsx per school year, 2020–2024 (2015–2019 only as .rar, F4.9), plus the national enrolment series 2002–2024 in each file. About 110 tables per year coded `II-<nivel>.<tema>.<n>`, about 60 of them by department; inventory in `docs/investigacion/mec_anuario_inventario.md` (from F4.1, pending). Only official gub.uy URLs, always read from each year's dataset page (folder and file names change). The INE *Anuario Estadístico Nacional* cap. 3.1 reproduces some of these tables: it is used **only as a control** of the load, never as a second source of the same figure.

Next: Censo 2023 microdata (segment level), Marco Censal 2023 (may contain zones), Encuesta Continua de Hogares (department level only; panel design since July 2021), INE price/wage series (country level), INE 2011–2023 correspondence table. To research: Catálogo Nacional de Datos Abiertos (CKAN API), IDE, Ministerio del Interior.
 
## 10. Glossary
 
| Spanish | Meaning |
|---|---|
| departamento | first-level administrative division (19) |
| sección censal | census section (historic judicial sections from 1963) |
| segmento censal | census segment; group of blocks in towns, area in rural land |
| zona censal | census zone; usually one block (not available yet) |
| localidad censal | census locality (town/city as defined by INE) |
| CCZ | Centro Comunal Zonal (Montevideo administrative zone) |
| ficha | profile page of a territory |
| captura | one download of a source file |
| ECH | Encuesta Continua de Hogares (household survey) |
 
