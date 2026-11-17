# Observatorio Uruguay — System Description
 
## 1. Purpose
 
Observatorio Uruguay collects public data about what happens in Uruguay's territory, stores it in its own database, and **links every data point to a territory** (department, census section, census segment, locality, Montevideo neighbourhood). A friendly web app lets anyone explore the data on a map, read a profile ("ficha") for each territory, see where every number comes from, and download it.
 
Product language: **Spanish (Uruguay)**. All UI copy is in Spanish. Code identifiers, table and column names are also in Spanish (they already are in phase 0). Keep it that way.
 
## 2. Constraints
 
- **One maintainer.** No servers, no managed database, no paid services. Everything must be rebuildable from scratch with one command.
- **Static-first.** Data pipeline runs in GitHub Actions; outputs are files (Parquet, GeoJSON/PMTiles, JSON); the app is a static site that reads those files.
- **Free hosting** (Cloudflare Pages or GitHub Pages).
- **Traceability over convenience.** Every value shown must point to its source file, download date and checksum.
- The INE website is unreliable for downloads. Original files are kept as assets of a GitHub release named `crudos` and the pipeline reads them from there first.
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
 
- Territory id: `INE-2023/<nivel>/<codigo>` (e.g. `INE-2023/segmento/1605601`).
- Hierarchy depto → sección → segmento is derivable from the code prefix.
- Segment → locality comes from the INE attribute `CODLOC` (stored in `correspondencias`).
- **Census zones (zona censal, 10-char code) are NOT in the INE package.** The segment is the finest unit available. Anything in the design that says "zona" must be implemented as "segmento" until zones are obtained.
- Geometries are versioned (`version_geo`). 2011 geometries will coexist with 2023 ones; INE publishes a 2011–2023 correspondence table.
## 4. Core data rules (non-negotiable)
 
1. **Store every value at the level where the source publishes it. Never aggregate population upward.** INE geolocates part of the administratively-enumerated population only at locality or department level. In 2023: departments sum to 3,495,947 people; sections/segments sum to 3,338,018 (−157,929; between 1.6% and 8.4% per department). Dwellings (viviendas) do match (±3).
2. Downward apportioning (department → smaller unit) is allowed only as an **estimate**, flagged `es_estimado = true`, and shown as such in the UI.
3. Every observation has a `captura_id` → source file name, sha256, processing date.
4. If an indicator does not exist at the level the user selected, the app **says so** and offers the nearest level that has it. It never fabricates or silently substitutes.
5. Raw files are immutable. If the checksum did not change, the source is not reprocessed.
6. The "LIMITE CONTESTADO" polygon has no observations of its own (INE repeats Artigas' counts on it).
## 5. Data model (implemented in phase 0)
 
```
territorios(id, nivel, codigo, nombre, depto, padre_id, version_geo, area_km2, codigo_iso, geometry)
observaciones(indicador, territorio_id, periodo, periodo_inicio, periodo_fin, tipo_periodo, valor, es_estimado, captura_id)
indicadores(codigo, nombre, unidad, columna_origen, fuente_id, nota)
capturas(id, fuente_id, archivo, sha256, fecha_proceso)
capturas_historial(id, fuente_id, archivo, sha256, fecha_proceso, resultado, detalle)  -- append-only, one row per run
fuentes(id, nombre, organismo, pagina, url_descarga, formato, licencia, frecuencia, estado, contacto,
        version_geo, temas[], nivel_mas_detallado, niveles_publicados[], notas[])  -- from fuentes/*.yml
correspondencias(origen_id, destino_id, tipo, peso, metodo)
VIEW v_observaciones  -- observaciones joined with territorio, indicador and captura
```
 
**Time periods (F2.2, implemented):** survey indicators refer to a 3-month moving quarter, not a year. `observaciones` has `periodo_inicio` (date, first day), `periodo_fin` (date, last day) and `tipo_periodo` (`censo`, `mes`, `trimestre_movil`, `trimestre`, `semestre`, `anio`). `periodo` stays as a human label (e.g. `2026-07/2026-09`). Phase-0 census rows are `tipo_periodo = censo`, `periodo_inicio = periodo_fin = 2023-01-01` with label `2023`.
 
**Level added in F2.3:** `municipio_mvd` (8 Montevideo municipalities). INE does not publish its geometry in the 2023 package, but `ccz_mvd_23_pg` has the attribute `NOMMUNICIPIO`; the geometry is derived by dissolving CCZ by municipality and recorded in `correspondencias` (ccz → municipio, `metodo = "disolución de CCZ por NOMMUNICIPIO"`). Each departamento is recorded as `pertenece_a` the `pais` territory (a relation only: no values are summed). Derived levels get `area_km2` measured on their geometry.
 
Planned additions: `eventos(id, dataset_id, fecha, geometry, territorio_id, atributos_json, captura_id)` for point data.

`resultado` in `capturas_historial`: `nuevo`, `reprocesado` (same original, `--forzar`), `sin cambios` (same sha256 as the last processed capture: not reprocessed) or `error`. Shared pipeline code lives in `pipeline/comun/` (M1).
 
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
 
Global header: logo + "Observatorio Uruguay", nav (Mapa · Fichas · Datos · Fuentes), search box "Buscar departamento, localidad o código INE".
 
**Mapa** (`/`)
- Left panel: Tema pills (Población, Vivienda, Hogares, Trabajo, Ingresos, Educación) → Indicador list (each shows source and the finest level available) → Nivel territorial (Departamento | Sección | Segmento) → Período.
- Center: choropleth map with real INE boundaries, legend, zoom controls, attribution "Límites: INE, unidades geoestadísticas 2023".
- If the chosen indicator is not published at the chosen level → orange notice explaining it and showing the nearest available level.
- Right panel: selected territory name, level and INE code; **locator mini-map** of Uruguay with the territory highlighted (circle around very small ones like Montevideo); main value with unit, national total, source + methodology link; 3 other indicators; buttons "Ver ficha completa" and "Descargar CSV".
- Mobile: topic chips row, indicator dropdown, map, bottom sheet with the selected territory.
**Ficha de departamento** (`/territorio/<nivel>/<codigo>`)
- Breadcrumb; name, level, code; 4 KPIs (población, superficie, densidad, localidades); locator map; actions: Comparar, Descargar CSV, Copiar enlace, Cómo citar.
- Section nav: Población · Vivienda y hogares · Trabajo e ingresos · Educación · Dentro del departamento · Fuentes.
- Indicator cards compare the territory vs. national total; population pyramid; annual series chart for survey indicators.
- "Dentro del departamento": table of child units (secciones / localidades / segmentos) with counts and "Ver en el mapa".
- Empty topics show an explicit "no sources loaded yet" notice instead of blank space.
- "Fuentes de esta ficha": each dataset with download date, link to original, methodology; citation text.
**Ficha de segmento** (designed as "zona"; implement as segmento)
- Breadcrumb Uruguay › Depto › Sección › Segmento; code chips; counts (personas, viviendas) with share of section and department; locator map + close-up of the unit among neighbours.
- "Más datos en los niveles que contienen este territorio": cards for sección and departamento with their indicators and links.
- "Hechos registrados" placeholder for future point sources; "En censos anteriores" placeholder for 2011 correspondence.
**Fuentes** (`/fuentes`) — catalog: summary counts (activas, en preparación, a relevar, última revisión), filters (search, organismo, nivel, estado), table (fuente, temas, nivel más detallado, frecuencia, última captura, estado badge), and a 4-step "Cómo trabajamos con cada fuente" explainer.
 
**Detalle de fuente** (`/fuentes/<id>`) — description, ficha técnica, indicators derived, capture history (date, file, sha256, result: nuevo / sin cambios / error), notes/warnings, "hasta dónde llega en el territorio", related tools, "Reportar un problema".
 
**Datos** (`/datos`) — not designed yet: bulk downloads (Parquet, CSV, GeoJSON) per level and per indicator, with license and citation.
 
## 9. Known sources (see `fuentes/` and project notes)
 
Active: INE unidades geoestadísticas 2023.
 
**Labor market (F2, next):** INE report *"Mercado de trabajo por área geográfica de residencia"*, monthly since February 2022. Official estimates for the 19 departments, the 8 Montevideo municipalities and, in recent reports, total país, as 3-month moving averages. Tables: activity, employment and unemployment rates (%); active, employed and unemployed (thousands); non-registration in social security (%). Published only as an HTML page (no spreadsheet): the pipeline must save each page and parse its tables. INE publishes no confidence intervals and warns: smaller departments are less precise; figures are by place of residence; seasonality (e.g. Maldonado); avoid single-period rankings. Example HTML: `https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/HTML/ECH/Mercado%20de%20trabajo%20por%20%C3%A1rea%20geogr%C3%A1fica/2026/Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.html` (July–September 2026). Country/Montevideo/Interior long series exist as xlsx (`series-historicas-actividad-empleo-desempleo`), without departments. ECH microdata are used only for indicators INE does not publish, labelled "calculado por el observatorio". **Only official INE sites are valid sources.**
 
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
 
