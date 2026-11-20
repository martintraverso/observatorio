# Observatorio Uruguay — Plan F3: Income by region (ECH)

Read `docs/SYSTEM.md` (data rules §4) and `docs/ACCEPTANCE_CRITERIA_ingresos.md` (AC-I1…I25) first. One story per PR; list the AC-I IDs in each PR. Stories are compatible with `/tomar-tarea` and `/trabajar`.

## Context and decisions (to be copied into `docs/SYSTEM.md` in F3.2)

**New level `region`** (decided by the maintainer on 2026-11-19): 3 territories without geometry — `INE-2023/region/interior` ("Interior del país"), `INE-2023/region/interior-5000` ("Interior: localidades de 5.000 o más habitantes"), `INE-2023/region/interior-menores` ("Interior: localidades pequeñas y zonas rurales"); parent `pais/UY`. They are the areas in which INE publishes ECH income series. `geometry` and `area_km2` are NULL; they are never drawn on the map and are skipped by geometry checks and exports, but appear in search, fichas and downloads. Relations in `correspondencias` (relation only, nothing is summed): `interior-5000` and `interior-menores` → `interior`; the 18 departments other than 01 → `interior`; `interior` → `pais`. Montevideo is `departamento/01`; total país is `pais/UY`.

**Income rules:** values stored exactly as published (full precision); the price base is part of the indicator (current pesos and pesos of January 2005 are different indicators; the observatory never deflates or converts); quarterly rows are `tipo_periodo = trimestre`, yearly totals `anio`; a changed file is a new capture whose values replace earlier ones for the same period (`vigente`), with a change summary in the report.

**No department income:** INE publishes no current official income or poverty figure by department (its 2025 poverty report has tables only by region; the department map is an image). MIDES publishes department series to 2023, but its income series looks mislabelled (values not consistent with current pesos) and its poverty series uses INE's 2006 method. Department income, if ever added, must be computed from ECH microdata and labelled "calculado por el observatorio" (F3.9, needs approval).

## Goal

Goal: INE's official income series for total país, Montevideo and the Interior (and its split by locality size), quarterly since 2016, in the database and in the app. Criteria: `docs/ACCEPTANCE_CRITERIA_ingresos.md` (AC-I1…I25). Decided by the maintainer on 2026-11-19: add the level `region` (no geometry).

**Order:** F3.1–F3.6 (data) can start now; F3.7 (app) after F3.4. Do not start F3.9 without the maintainer.

**Sources (official INE only):**
- Page: https://www.gub.uy/instituto-nacional-estadistica/datos-y-estadisticas/estadisticas/series-historicas-ech-ingresos-personas-hogares
- Files: `https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/SERIES%20Y%20OTROS/ECH/Series%20hist%C3%B3ricas/Ingresos%20de%20las%20personas%20y%20los%20hogares/<archivo>.xlsx` (ECHING07…ECHING14, ECHINGRESOS2, ECHINGRESOS3, ECHINGRESOS_4, _6, _7, _8, _9). Some links on the page point to the folder `Ingresos%202024/` instead; take the URL from the page, do not assume.
- Note on the 2025 income concept: `https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/SERIES%20Y%20OTROS/ECH/Series%20hist%C3%B3ricas/Ingresos%202024/Nota%20aclaratoria%20a%20series.pdf`
- Quarterly reports "Ingresos de los hogares y de las personas" on the INE site (find the latest from the INE publications list; read it for the headline variant and the YDA change).

Findings from the research (2026-11-19, files read directly): one sheet per file; title in rows 1–3; two-row header ("Interior" split in Total / 5.000 o más / pequeñas y rurales); a year row before each block; rows "Enero - Marzo/16" … and "Total 2016"; full-precision numbers; footnotes at the end ("sujetas a revisión", "(1) Cifras actualizadas a noviembre 2026"). Medians link: 404.

### F3.1 — Explore and save fixtures (spike, time-boxed)
1. Download every xlsx linked on the page; record code, title, URL, HTTP status and sha256.
2. Save 3 small fixtures in `tests/fixtures/ech_ingresos/` (ECHING07, ECHING09, ECHINGRESOS2). If a file is large, cut it with a script that keeps the original layout.
3. Confirm from INE material: monthly vs. other reference period ("por mes"), the headline variant INE uses in its quarterly report, and whether the 2016– series were recomputed with YDA or are comparable across 2025. Write it down; do not assume.
4. Write `fuentes/ine_ech_ingresos_series.yml` (AC-I18), with `estado: en preparación` and `cargar: true`.

Done when: fixtures committed; registry written; open questions listed in the PR.

### F3.2 — Region level
Add `region` with its 3 territories and relations (AC-I1, AC-I2); exempt it from geometry checks and exports; include it in the search index (AC-I3). Copy the "Context and decisions" section above into `docs/SYSTEM.md` (§3 territorial model, §5 data model, §9 sources) in the same PR.

### F3.3 — Parser
`pipeline/ech_ingresos.py` with a pure function `parsear_serie(xlsx_bytes, codigo) -> DataFrame` (no network): column → territory (AC-I7), row → period (AC-I8), indicator per file (AC-I9), full precision (AC-I10). Golden tests (AC-I11).

### F3.4 — Capture and load
Download step reading URLs from the registry (AC-I4), errors reported but not fatal (AC-I5), revisions as new captures with a change summary (AC-I6), load through `pipeline/comun/`.

### F3.5 — Quality checks and report
AC-I12…I17 as pipeline checks; income section in `reporte_validacion.md` (files, status, periods, changes, latest values per territory).

### F3.6 — Automation
Weekly data workflow includes the income source (AC-I19). PRs that change workflows wait for the maintainer.

### F3.7 — App
Map notice + regional comparison (AC-I20); series in país, Montevideo and region fichas with variant and price-base selectors (AC-I21); links from other fichas (AC-I22); region ficha layout (AC-I23); labels and notes (AC-I24); CSV (AC-I25). Follow the M10 criteria (message styles, collapsible notes, chart ticks).

### F3.8 — Optional: more tables
Mean income of recipients by income source (ECHINGRESOS_4, _6–_9) and of the employed (total país); medians when INE fixes the link. Only if the maintainer asks.

### F3.9 — Later, needs a decision: income by department
No official current department figures exist. Options to bring to the maintainer: compute from ECH annual microdata with survey weights and margins of error, labelled "calculado por el observatorio"; or use MIDES' series only if MIDES confirms its unit and method. Do not implement without approval.
