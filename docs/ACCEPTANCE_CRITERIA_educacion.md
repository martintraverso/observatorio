# Observatorio Uruguay — Acceptance Criteria: Education (F4)
 
**Scope.** Every table of the MEC *Anuario Estadístico de Educación* for 2020–2024 (xlsx), plus the national enrolment series 2002–2024. This file goes with `docs/PLAN_educacion.md`.
 
**Conventions.** Same as `docs/ACCEPTANCE_CRITERIA.md`:
- **[auto]** = automated test;
- **[manual]** = checked by hand, with evidence in the PR.
The general criteria (AC-P*, AC-T*, AC-W*, AC-G*) and the visual criteria in `docs/ACCEPTANCE_CRITERIA_UI.md` (AC-V*) still apply.
 
**Source.** MEC, División de Investigación y Estadística. Use only official gub.uy URLs. The INE Anuario Estadístico Nacional cap. 3.1 is used only as a control.
 
**Territories.** `pais/UY`, `departamento/*` and `region/interior` (from F3.2). Nothing is loaded below departamento.
 
**Decisions taken on 2026-11-23:**
- **D1:** all tables, in two waves, with types A / B / C.
- **D2:** derived rates are allowed.
- **D3:** the map default is the promotion rate in public primary.
**Inventory and registry**
- **AC-E1** [manual] `docs/investigacion/mec_anuario_inventario.md` lists, for each year 2020–2024:
  - every sheet, with its table code, title, type (A = rows by department; B = national totals by category; C = rows by institution or centre) and wave (1 or 2);
  - its header rows, and its "Fuente:" and "Nota:" text.
  It also has a table of codes × years showing which codes are present, and the list of every change in column meaning between years.
- **AC-E2** [manual] `fuentes/mec_anuario_educacion.yml` documents:
  - the MEC page;
  - one entry per year: dataset page, xlsx URL taken from that page (never built), publication and update dates, sha256;
  - for every table and year: type, wave, and the mapping from header path to indicator id and unit; tables not loaded are listed with a reason;
  - license and citation as MEC publishes them.
  Maintainer notes go in `notas_internas` (never rendered, AC-V19).
- **AC-E3** [manual] `docs/SYSTEM.md` (§5, §9) contains the "Context and decisions" section of the plan. The indicator catalogue has the fields `es_derivado` (bool) and `formula` (text, empty for published values).
**Capture**
- **AC-E4** [auto] Each year's xlsx is a capture. It is saved unchanged under `datos/crudo/mec_anuario/<anio>.xlsx` and in the release `crudos`, with its official URL, sha256 and download date.
- **AC-E5** [auto] A year whose file returns an error is reported in `reporte_validacion.md` and does not fail the run. The other years are still loaded.
- **AC-E6** [auto] A changed file for the same year (different sha256) is a new capture marked `vigente`. Its values replace the earlier ones for that year, and the report lists how many values changed and the largest change. Unchanged files are skipped (AC-P8).
- **AC-E7** [auto] The 2002–2024 series is taken from the latest anuario. Where it overlaps a yearly table, both are kept, and a difference shows as a warning in the report.
**Parsing**
- **AC-E8** [auto] Row labels map to territories by normalized name (accents and case ignored):
  - "TOTAL" → `pais/UY`;
  - "MONTEVIDEO" → `departamento/01`;
  - each of the 18 department names → `departamento/<código INE>`;
  - "RESTO DEL PAÍS" → `region/interior`.
  An unknown row label in a type A table fails the run.
- **AC-E9** [auto] Merged header rows are flattened into paths (e.g. `PÚBLICA/SEXO/MUJER`) and mapped to indicators through the registry. A header path missing from the mapping fails the run, and so does a mapped path missing from the file.
- **AC-E10** [auto] The year is read from the table title ("…, 2024)") and must equal the file's year. Values are stored as `tipo_periodo = anio`, from `YYYY-01-01` to `YYYY-12-31`, label `YYYY`.
- **AC-E11** [auto] Counts are stored as published integers. "-", "…", "s/d" and empty cells are not data: no row is created, and the report counts them per table.
- **AC-E12** [auto] Each table's "Fuente:" and "Nota:" rows are kept in the capture metadata, linked to the table code, and are never parsed as data.
- **AC-E13** [auto] A breakdown whose meaning changes between years becomes a different indicator. For example, II-2.2.1 sex totals cover all administrations in 2023 and only public schools in 2024. No indicator mixes the two meanings. Test: the 2023 and 2024 sex values of II-2.2.1 land in different indicator ids.
- **AC-E14** [auto] The sheet "MATRÍCULA DEL SISTEMA 2002-2024" loads into `pais/UY` with one value per year, level and administration.
- **AC-E15** [auto] Golden tests on the saved fixtures:
  | Table | Year | Expected values |
  |---|---|---|
  | II-2.2.1 | 2024 | TOTAL 284.944 · pública 237.385 · privada 47.559 · pública varón 122.200, mujer 115.185 |
  | | | MONTEVIDEO 102.182 · RESTO DEL PAÍS 182.762 · Artigas 7.209 · Canelones 48.638 |
  | II-2.2.1 | 2023 | TOTAL 287.805 · varón 147.955 · mujer 139.655 |
  | II-2.2.13 | 2024 | pública: TOTAL promovidos 232.567, no promovidos 4.818 · MONTEVIDEO 71.109 / 2.616 |
  | National series | 2024 | TOTAL SISTEMA 1.042.564 · primaria común 284.944 |
**Derived rates (D2)**
- **AC-E16** [auto] The pipeline computes derived indicators:
  - promotion rate = promovidos / (promovidos + no promovidos);
  - % private enrolment = privada / total;
  - ~~% insufficient attendance, from the counts in II-2.2.18~~: left out by the maintainer (2026-11-23, PR #186). II-2.2.18 publishes the counts but no enrolment, so there is no denominator in the same table.
  Each derived indicator has `es_derivado = true`, its `formula`, and the unit "%". Numerator and denominator must come from the same table, year, territory and scope; if one of them is missing, no rate is produced. Test: II-2.2.13 2024 pública TOTAL promotion rate = 232.567 / 237.385 = 97,97 %.
**Data quality checks** (failures stop the run unless marked as a warning)
- **AC-E17** [auto] In type A tables, MONTEVIDEO plus the 18 departments adds up to TOTAL for every count indicator.
- **AC-E18** [auto] "RESTO DEL PAÍS" = TOTAL − MONTEVIDEO. Where this fails, or `region/interior` does not exist, the region rows are skipped and reported; the run does not stop.
- **AC-E19** [auto] Breakdowns add up to their total:
  - pública + privada = total;
  - urbano + rural = total;
  - varón + mujer = the total of the same scope;
  - in type B and C tables, categories = the table total.
- **AC-E20** [auto] All counts are ≥ 0 and every rate is between 0 and 100. No education observation exists below departamento. No type B or C row is attached to a department unless the table names the department in that row.
- **AC-E21** [auto] Every type A table yields one value per indicator and year for the 20 territories (TOTAL, MONTEVIDEO, RESTO DEL PAÍS and the 17 other departments), except the gaps listed in the registry.
- **AC-E22** [auto] *(warning only)* An indicator that changes by more than ±20 % between consecutive years in the same territory is listed in the report.
- **AC-E23** [auto] *(warning only)* For 2023 and 2024, loaded values are compared with INE Anuario cap. 3.1 where the INE table is the same measure (e.g. 3.1.6). Differences are listed in the report. INE values are never loaded.
- **AC-E24** [auto] `reporte_validacion.md` has an education section with:
  - files and HTTP status, and years loaded;
  - tables mapped / listed without loading / missing;
  - skipped cells, warnings and changes;
  - the latest values for país and Montevideo.
**Automation**
- **AC-E25** [auto] The weekly data workflow checks the MEC page for a new or updated anuario.
  - A new or updated file is downloaded and inventoried.
  - A year without a mapping in the registry is **not loaded**: the run opens one issue "Nuevo anuario MEC <año>: revisar mapeo", labelled `necesita-humano`, and does not duplicate it on later runs.
**App**
- **AC-E26** [manual] The map has the topic "Educación".
  - The default is a department choropleth of the promotion rate in public primary for the latest year (D3).
  - Selectors for level (primaria / media básica / media superior), indicator and year.
  - The legend says the value is "calculado por el observatorio a partir de MEC".
- **AC-E27** [manual] Department, país and Interior fichas have an "Educación" section with:
  - the yearly series 2020–2024 (line chart);
  - enrolment by administration;
  - promotion and graduates;
  - schools and teachers.
  The país ficha also shows the 2002–2024 enrolment series and the type B and C tables, grouped by level.
- **AC-E28** [auto] Fichas of section, segment, locality, barrio and CCZ say "Educación: datos por departamento" and link to the department ficha (AC-V24 pattern).
- **AC-E29** [manual] Next to each education value the app shows:
  - the unit and the year;
  - "Fuente: MEC, Anuario Estadístico de Educación <año>, cuadro <código>";
  - the table's notes, in the collapsible notes block;
  - "calculado por el observatorio" for derived values.
- **AC-E30** [manual] When a breakdown changes meaning between years (AC-E13), the chart shows two separate series, not one joined line, and a note explains the change.
- **AC-E31** [auto] CSV downloads include education rows with `tipo_periodo`, `periodo_inicio`, `periodo_fin`, unit, table code and `es_derivado`.
**Wave 2 and completeness**
- **AC-E32** [manual] The page "Catálogo de educación" lists every table, with code, title, type, years available and a link to where it is shown.
- **AC-E33** [auto] Every table code of every year 2020–2024 is either mapped in the registry or listed there with a reason (e.g. "sin datos numéricos", "duplicado de II-x.y.z"). A table with neither fails the test.
 