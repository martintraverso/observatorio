# Observatorio Uruguay — Plan F4: Education by department (MEC Anuario)
 
Read `docs/SYSTEM.md` (data rules §4) first. Then read `docs/ACCEPTANCE_CRITERIA_educacion.md` (AC-E1…E33). One story per PR, and each PR lists its AC-E IDs. Stories are compatible with `/tomar-tarea` and `/trabajar`.
 
## Context and decisions (to be copied into `docs/SYSTEM.md` in F4.2)
 
**Source.** The MEC *Anuario Estadístico de Educación* (División de Investigación y Estadística, Dirección Nacional de Educación) is published once a year as an xlsx. The 2024 edition was published on 2026-01-02 and updated on 2026-02-13. Use only official gub.uy URLs.
 
**INE as a control, not a source.** The INE *Anuario Estadístico Nacional* cap. 3.1 reproduces about 10 of these tables by department. It is used only to cross-check the load (F4.5). It is never loaded as a second source of the same figure.
 
**Territories.**
 
| Row label | Territory |
|---|---|
| "TOTAL" | `pais/UY` |
| "MONTEVIDEO" | `departamento/01` |
| The 18 department names | `departamento/<código INE>` (mapped by name; an unknown name fails the run) |
| "RESTO DEL PAÍS" | `region/interior` (level from F3.2) |
 
- Nothing below departamento is published, and nothing is estimated downward.
- "RESTO DEL PAÍS" rows are loaded only if two things hold:
  - `region/interior` exists;
  - the row equals TOTAL − MONTEVIDEO.
  Otherwise the rows are skipped and reported.
**Period.** Each file covers one school year (March–December), which falls inside the calendar year. Store it as `tipo_periodo = anio`, with `periodo_inicio` = YYYY-01-01, `periodo_fin` = YYYY-12-31 and label `YYYY`.
 
**One year per file.** Each table holds a single year ("Todo el país, 2024"). Series are built by loading one anuario per year. Each anuario is its own capture, so a revised table in a later edition does **not** overwrite an earlier year unless that year is republished in a new version of the same file.
 
**Indicators are counts as published.**
- There is one indicator per measure and breakdown, for example:
  - `edu_mat_primaria_comun` (total), `edu_mat_primaria_comun_publica` and `edu_mat_primaria_comun_privada`;
  - `edu_mat_primaria_comun_publica_mujer`;
  - `edu_prim_promovidos_publica` and `edu_prim_no_promovidos_publica`.
- Units are "estudiantes", "establecimientos", "docentes" or "grupos".
- A breakdown whose meaning changes between years becomes a **different indicator**, never the same one. Example: in II-2.2.1, sex covers all students in 2023 but only public students in 2024, because private schools stopped reporting sex.
**Rates are derived** (decision D2): promotion rate and % private enrolment. (% insufficient attendance was left out on 2026-11-23: II-2.2.18 has no denominator in the same table.)
 
**Notes travel with the value.** Each table's "Fuente:" and "Nota:" rows are kept in the capture metadata and shown in the app, for example:
- "Pública no incluye JICI";
- rendimiento counts end-of-year results, not initial enrolment;
- Montevideo has no rural public primary.
## Goal
 
Load every table of the MEC anuario 2020–2024 into the database and the app, plus the national enrolment series 2002–2024. That covers enrolment, schools, promotion, graduates, insufficient attendance, teachers, groups and every level from inicial to universitaria. Tables by department are loaded by department; the rest are loaded at país.
 
**Order:**
- F4.1 first.
- F4.2–F4.6 after F4.1, for wave 1. The "RESTO DEL PAÍS" rows need F3.2.
- F4.7 (app) after F4.4.
- F4.8 (wave 2) after F4.5.
- Do not start F4.9 without the maintainer.
**Sources:**
- Page: https://www.gub.uy/ministerio-educacion-cultura/datos-y-estadisticas/datos (4 pages of results). Each year has its own dataset page with the file link. The upload folder (`files/2026-02/`, `files/2025-04/` …) and suffixes such as `_0` change, so take every URL from the dataset page and never build it.
- Known files (read on 2026-11-23):
  - 2024: `https://www.gub.uy/ministerio-educacion-cultura/sites/ministerio-educacion-cultura/files/2026-02/Anuario%20Estad%C3%ADstico%20de%20Educaci%C3%B3n%202024.xlsx`
  - 2023: `…/files/2025-04/Anuario%20Estad%C3%ADstico%20de%20Educaci%C3%B3n%202023.xlsx`
  - 2022: `…/files/2023-12/…2022_0.xlsx`
  - 2021: `…/files/2023-01/…2021.xlsx`
  - 2020: `…/files/2022-09/…2020_0.xlsx`
  - 2015–2019: `.rar` (out of scope, F4.9)
- Control: INE Anuario Estadístico Nacional 2025, cap. 3 → 3.1 "Educación e investigación": https://www.gub.uy/instituto-nacional-estadistica/comunicacion/publicaciones/anuario-estadistico-nacional-2025-vol-102/capitulo-3-aspectos-sociales
**Findings from the research** (2026-11-23; the 2024 and 2023 files were read directly):
 
*Layout of the 2024 file*
- **Sheets:** 125 in total.
  - Fixed sheets: PRESENTACIÓN; "MATRÍCULA DEL SISTEMA 2002-2024"; one separator sheet per level; CONTROL sheets.
  - **110 tables** coded `II-<nivel>.<tema>.<n>`.
    - Levels: 1 primera infancia e inicial, 2 primaria, 3 media básica, 4 media superior, 5 terciaria no universitaria, 6 formación en educación, 7 universitaria, 8 jóvenes y adultos.
    - Topics: .1 establecimientos, .2 estudiantes (matrícula y rendimiento), .3 docentes, .4 grupos.
- **Tables by department:** about 60. All use the row order TOTAL, MONTEVIDEO, RESTO DEL PAÍS, then the 18 departments. Universitaria and terciaria are mostly by institution, not by department.
- **Table layout:**
  - Title row: "Cuadro II-x.y.z – <título> (Todo el país, 2024)".
  - Headers: 2–4 rows with merged cells, e.g. TOTAL / FORMA DE ADMINISTRACIÓN → PÚBLICA / PRIVADA → SEXO → VARÓN / MUJER.
  - Footer: "Fuente:" and "Nota:" rows.
*2023 compared with 2024*
- The 2023 file has 122 sheets and 107 tables.
- Every 2023 code also exists in 2024. 2024 adds II-3.2.12, II-4.2.15 and II-8.4.4.
- Row order is the same in both years.
- Column meaning can differ by year (see II-2.2.1 above).
*Control values for golden tests*
 
| Table | Year | Values |
|---|---|---|
| II-2.2.1 (matrícula primaria común) | 2024 | TOTAL 284.944 (pública 237.385, privada 47.559; pública varón 122.200, mujer 115.185) |
| | | MONTEVIDEO 102.182 · RESTO DEL PAÍS 182.762 · Artigas 7.209 · Canelones 48.638 |
| II-2.2.1 | 2023 | TOTAL 287.805 (varón 147.955, mujer 139.655, all administrations) |
| II-2.2.13 (rendimiento primaria pública) | 2024 | TOTAL promovidos 232.567, no promovidos 4.818 · MONTEVIDEO 71.109 / 2.616 |
| "MATRÍCULA DEL SISTEMA 2002-2024" | 2024 | TOTAL SISTEMA 1.042.564 · primaria común 284.944 |
| INE 3.1.6 (media básica general pública) | 2024 | varón / mujer: Total 50.776 / 54.572 · Montevideo 15.898 / 16.496 · Artigas 1.316 / 1.462 |
| INE 3.1.8 (aprobación media básica pública, %) | 2024 | general / vocacional: Total 89,5 / 77,5 · Montevideo 84,4 / 73,4 · Artigas 94,0 / 82,8 |
 
## Decisions (taken by the maintainer on 2026-11-23)
 
- **D1 — All tables.** Every table of the anuario is loaded: the 110 tables of 2024 and their equivalents in 2020–2023. F4.1 classifies each table into one of three types:
  | Type | What the table has | How it is loaded |
  |---|---|---|
  | **A** | Rows by department (TOTAL / MONTEVIDEO / RESTO DEL PAÍS / 18 departments) | To `departamento/*`, `pais/UY` and `region/interior` |
  | **B** | National totals only, broken down by category (grade, age, institution, area…) | To `pais/UY`; each category is part of the indicator id |
  | **C** | Rows by another unit (institution, campus, centre) | To a department only where the table names it for each row; otherwise to `pais/UY` as in B |
  An institution is never a territory.
  Work goes in two waves:
  - **Wave 1** is the set below. It goes first and its tables also feed the map.
  - **Wave 2** is every other table: levels 5, 6, 7 and 8, grupos, docentes by detail, and the remaining B and C tables.
  Wave 1 (to be confirmed in F4.1 against the actual titles):
  | Level | Tables |
  |---|---|
  | Inicial | II-1.1.1, II-1.1.2 (establecimientos DGEIP / INAU); II-1.2.x (matrícula inicial) |
  | Primaria | II-2.1.1–2.1.4 (establecimientos, incl. urbano/rural); II-2.2.1 (matrícula común); II-2.2.13–2.2.15 (rendimiento); II-2.2.16–2.2.17 (egresados); II-2.2.18 (asistencia insuficiente y abandono intermitente); II-2.3.x (docentes) |
  | Media básica | II-3.1.x (establecimientos); II-3.2.x (matrícula DGES / DGETP); II-3.2.10–12 (rendimiento) |
  | Media superior | II-4.1.1 (establecimientos); II-4.2.x (matrícula); II-4.2.13–15 (rendimiento) |
  | National series | "MATRÍCULA DEL SISTEMA 2002-2024" → `pais/UY`, every year, by level and administration |
- **D2 — Derived rates: approved.**
  - The observatory computes promotion rate = promovidos / (promovidos + no promovidos) and % private enrolment from the stored counts. % insufficient attendance is left out (maintainer, 2026-11-23): II-2.2.18 has no enrolment to divide by.
  - Each rate is stored as its own indicator with `es_derivado = true`, the formula, and the label "calculado por el observatorio a partir de MEC".
  - Rates are never mixed with the INE percentages (3.1.8), which are used only as a control.
  Rates are computed only where numerator and denominator come from the same table, year and scope.
- **D3 — Default map indicator: approved.** Promotion rate in public primary, latest year.
- **D4 — Data from another year: load it with its real year** (decided 2026-11-23, PR #177). Some tables, or parts of them, say in their footer that the data are from an earlier year. For example, private DGEIP in the 2021 anuario is from 2020, and II-1.3.2 in the 2024 anuario is from 2022; F4.1 lists 49 table-years. Those values are stored with the period of the year the footer states, and the capture of the anuario that publishes them. The footer note goes with the value.
  - If the value is already loaded (the anuario of that year publishes the same indicator for the same territory), it is not loaded again. That anuario's value stays, and a difference is a warning in the report.
  - The year in the title still has to equal the file's year (AC-E10). The footer only changes the period of the columns it names.
- **D5 — Header paths that the layout cannot resolve are mapped by hand in F4.3** (decided 2026-11-23). Some cells are merged over fewer columns than the group they label, so the path read from the layout is wrong for a few totals (II-2.1.4 C, II-1.2.3 C, II-1.2.4, II-4.2.14, II-1.2.5). Other columns share a path (`repetida` in the registry, e.g. the three «SEXO/Varón» of II-4.2.4). F4.3 maps these columns by hand and checks each one with sums on the fixtures.
- **D6 — Concepts follow the latest anuario** (decided 2026-11-23). A table's type and layout may change between years, and that is expected. Indicators keep the concepts of the latest anuario's tables (2024 today); earlier years are mapped to those concepts wherever the meaning is the same. Where it is not, AC-E13 applies.
- **D7 — Repeated columns are not loaded twice** (decided 2026-11-23). In II-2.2.1 of 2024, the sex totals repeat the public columns, so they are marked `omitir` and not loaded.
- **"RESTO DEL PAÍS" = TOTAL − MONTEVIDEO** (confirmed by the maintainer, 2026-11-23). The AC-E18 check stays as a control.
## Stories
 
### F4.1 — Explore and save fixtures (spike, time-boxed)
Criteria: AC-E1, AC-E2.
 
 
**Files**
1. Collect from the MEC page the dataset page of every anuario 2020–2024, the xlsx URL on it, and its publication and update dates.
2. Download each xlsx and record its URL, HTTP status, size and sha256.
**Inventory**
3. Inventory each year: sheet names, table codes, titles, type (A / B / C, see D1), wave, the header rows, and the "Fuente" and "Nota" text.
4. Commit the inventory as `docs/investigacion/mec_anuario_inventario.md`, with one table of codes × years showing which codes are present.
5. Compare the headers of every table across 2020–2024, starting with wave 1, and list every change in column meaning (as in II-2.2.1). Do not assume a column means the same every year.
 
**Fixtures and registry**
6. Save the fixtures in `tests/fixtures/mec_anuario/`: the 2024 and 2023 files cut by a script down to the wave 1 tables plus at least two tables of type B and two of type C, keeping the original layout, merged cells and footers. Commit the script.
7. Write `fuentes/mec_anuario_educacion.yml` with `estado: en preparación` and `cargar: true`. It holds:
   - the page and one entry per year (URL, sha256, dates);
   - for each wave 1 table, the indicator mapping for each year (wave 2 tables are listed with their type and mapped in F4.8): header path → indicator id, unit.
**Done when:**
- The inventory, fixtures, script and registry are committed.
- Every table of every year has a type and a wave.
- The PR lists every semantic change between years.
- The PR lists open questions, for example whether "Resto del país" always equals Total − Montevideo.
### F4.2 — Registry rules and SYSTEM.md
Criteria: AC-E3.
 
- Copy "Context and decisions" into `docs/SYSTEM.md` (§5 data model, §9 sources), including the rule that a breakdown changing meaning becomes a new indicator.
- Add `es_derivado` and `formula` to the indicator catalogue if they are not already there; they are needed for D2.
- If F3.2 has merged, document the `region/interior` mapping.
### F4.3 — Parser
Criteria: AC-E8…E15.
 
- `pipeline/mec_anuario.py` with a pure function `parsear_cuadro(xlsx_bytes, codigo, anio, mapeo) -> DataFrame`. It makes no network calls and is driven by the registry mapping.
- **Rows → territories.** Map by normalized name, ignoring accents and case. An unknown row fails the run.
- **Headers → indicators.** Flatten the merged header rows into paths ("TOTAL", "PÚBLICA/SEXO/MUJER") and map them to indicators. A path that is not in the mapping fails the run, and so does a mapped path that is missing.
- **Year.** It is taken from the title ("…, 2024)") and must equal the file's year.
- **Values.**
  - Store integers as published.
  - "-", "…" and empty cells are not data: the parser counts them and reports them.
- **Footers.** "Fuente:" and "Nota:" rows go to the capture metadata, not to the data.
- **National series.** `parsear_serie_matricula(xlsx_bytes)` reads the "MATRÍCULA DEL SISTEMA 2002-2024" sheet into `pais/UY` × year.
- **Golden tests:** the control values above for 2024 and 2023.
### F4.4 — Capture, load and derived rates
Criteria: AC-E4…E7, AC-E16.
 
- The download step reads the URLs from the registry.
- An error on one file is reported but is not fatal; the other years still load.
- Each year's file is a capture: the raw xlsx is saved unchanged in `datos/crudo/mec_anuario/<anio>.xlsx` and in the release `crudos`.
- A changed sha256 for the same year is a new `vigente` capture, and the report summarizes the changes (count, largest change).
- The national series comes from the latest anuario. Where it overlaps a yearly table, both are kept, and a mismatch is a warning.
- Load through `pipeline/comun/`.
- Compute the D2 rates from the loaded counts as derived indicators.
### F4.5 — Quality checks and report
Criteria: AC-E17…E24.
 
Add pipeline checks. Failures stop the run unless marked as a warning.
 
**Checks**
- **Departments.** The 18 departments plus MONTEVIDEO add up to TOTAL for every count indicator.
- **Resto del país.**
  - Each row = TOTAL − MONTEVIDEO.
  - A failure there **skips** the region rows and does not stop the run.
- **Breakdowns.**
  - pública + privada = total.
  - varón + mujer = the total of the same scope (pública in 2024, all in 2023).
  - urbano + rural = total.
- **Values.**
  - All counts are ≥ 0.
  - No education observation exists below departamento.
  - Every type A table yields 20 rows (TOTAL, Montevideo, Resto del país and the 17 other departments) per indicator and year, except where the registry lists known gaps.
- **Change between years** *(warning)*: an indicator that changes by more than ±20 % from one year to the next in a territory.
- **INE cross-check** *(warning)*: for 2023 and 2024, compare the loaded values with INE 3.1.x where the INE table is the same measure, and list the differences.
**Report**
- `reporte_validacion.md` gets an education section: files and status, years loaded, skipped cells, notes, changes, and the latest values for país and Montevideo.
### F4.6 — Automation
Criteria: AC-E25.
 
- The weekly data workflow also checks the MEC page for a new anuario, or a new version of an existing one.
- A new year is downloaded and inventoried, but **not loaded** until its mapping is in the registry. The run opens an issue labelled `necesita-humano` ("Nuevo anuario MEC <año>: revisar mapeo").
- PRs that change workflows wait for the maintainer.
### F4.7 — App
Criteria: AC-E26…E31.
 
- **Map.** Add a topic "Educación".
  - Department choropleth of the D3 indicator, with a selector for level (primaria / media básica / media superior) and year.
- **Fichas: content.**
  - Department, país and Interior fichas get an "Educación" section:
    - a yearly series chart (2020–2024);
    - enrolment by administration;
    - promotion and graduates;
    - schools and teachers;
    - for país, the 2002–2024 national enrolment series.
  - Fichas below department say "Educación: datos por departamento" and link to the department ficha (AC-V24 pattern).
- **Fichas: labels and notes.**
  - Next to each value show the unit, the year, "Fuente: MEC, Anuario Estadístico de Educación <año>", the table code, and the table's notes in the collapsible notes block.
  - Derived values say "calculado por el observatorio".
  - Where a breakdown changes meaning between years, the series is broken, not joined, and a note explains why.
- **Downloads.** CSV downloads include the education rows with the table code and `es_derivado`.
- Follow the M10 criteria: message styles, collapsible notes, chart ticks.
### F4.8 — Wave 2: the remaining tables
Criteria: AC-E19, AC-E20, AC-E32, AC-E33 (plus AC-E8…E13 for every new mapping).
 
- Map every table not in wave 1 (D1), following the types from the F4.1 inventory. Split the work into one PR per level: II-1 to II-4 remainders, II-5, II-6, II-7, II-8.
- **Type A tables** get the full set of F4.5 checks.
- **Type B and C tables:**
  - categories must add up to their table total;
  - no row goes to a department unless the table names it.
- **App:**
  - type A tables appear in department fichas;
  - type B and C tables appear in the país ficha, grouped by level;
  - the education catalogue page lists every table with its code, title, type and years.
- Rates beyond the wave 1 set are added only where D2's same-table rule holds.
Done when every table code of every year is either mapped in the registry or listed in it with a reason (for example "sin datos numéricos" or "duplicado de II-x.y.z").
 
### F4.9 — Later, needs a decision: 2015–2019
- Those years are `.rar` files.
- Options to bring to the maintainer:
  - extract them in CI (unrar or 7z) and map them, if their layout matches;
  - stop the series at 2020.
- Check first that the 2015–2019 table codes and layout match the 2020+ files.
- Do not implement without approval.
 