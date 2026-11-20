# Observatorio Uruguay — Acceptance Criteria: Income (F3)

Scope: INE income series by region (ECH historical series). Companion of `docs/PLAN_ingresos.md`. Same conventions as `docs/ACCEPTANCE_CRITERIA.md`: **[auto]** = automated test, **[manual]** = checked by hand with evidence in the PR. All general criteria (AC-P*, AC-T*, AC-W*, AC-G*) and the visual criteria in `docs/ACCEPTANCE_CRITERIA_UI.md` (AC-V*) still apply.

Source: INE, *Series históricas ECH Ingresos de las Personas y los Hogares* (xlsx, quarterly since 2016). Only official INE URLs. Territories: `pais/UY`, `departamento/01` (Montevideo) and the new level `region` (no geometry).

**Territory: region level**
- **AC-I1** [auto] Level `region` has exactly 3 territories: `INE-2023/region/interior` ("Interior del país"), `INE-2023/region/interior-5000` ("Interior: localidades de 5.000 o más habitantes"), `INE-2023/region/interior-menores` ("Interior: localidades pequeñas y zonas rurales"); parent `pais/UY`; `geometry` and `area_km2` are NULL.
- **AC-I2** [auto] `correspondencias` has `pertenece_a` for `interior-5000` → `interior`, `interior-menores` → `interior`, and the 18 departments other than 01 → `interior`. No value is computed from these relations.
- **AC-I3** [auto] Geometry checks (AC-T3), web geometry exports (AC-W1, AC-W2) and PMTiles skip `region`; `territorios_index.json` includes the 3 regions with `bbox = null` (AC-W3), so search finds "Interior".

**Capture**
- **AC-I4** [auto] Each table is a capture: the xlsx is saved unchanged under `datos/crudo/ech_ingresos/<archivo>.xlsx` (and in release `crudos`) with its official URL, sha256 and download date. The list of files and URLs lives in `fuentes/ine_ech_ingresos_series.yml`.
- **AC-I5** [auto] A file that returns an error (e.g. the medians, HTTP 404 on 2026-11-19) is reported in `reporte_validacion.md` and does not fail the run; the other files are still loaded.
- **AC-I6** [auto] A changed file (different sha256) is a new capture marked `vigente`; its values replace earlier ones for the same indicator, territory and period, and the report lists how many values changed and the largest change. Unchanged files are skipped (AC-P8).

**Parsing**
- **AC-I7** [auto] Columns map to territories: "Total País" → `pais/UY`; "Montevideo" → `departamento/01`; "Interior · Total" → `region/interior`; "Localidades de 5.000 o más hab." → `region/interior-5000`; "Localidades Pequeñas y Zonas rurales" → `region/interior-menores`, handling the two-row header. An unknown column fails the run.
- **AC-I8** [auto] Row labels map to periods: "Enero - Marzo/16" → `trimestre` 2016-01-01…2016-03-31 (label `2016-T1`), likewise for the other quarters; "Total 2016" → `anio` 2016-01-01…2016-12-31 (label `2016`). Year separator rows and footnotes are not data. Footnote markers such as "(1)" are removed from labels and their text ("Cifras actualizadas a noviembre 2026") is kept in the capture metadata.
- **AC-I9** [auto] Indicators are distinct per measure, unit and price base. Minimum set (current prices, monthly pesos): `ing_hogar_medio` and `ing_pc_medio`, each in the four variants `cagu_cvl`, `sagu_cvl`, `cagu_svl`, `sagu_svl` (ECHING07–14); January 2005 prices: `ing_hogar_medio_sagu_svl_ene2005`, `ing_pc_medio_sagu_svl_ene2005` (ECHINGRESOS2–3). Unit text: "pesos corrientes por mes" / "pesos de enero de 2005 por mes" (confirm "por mes" in F3.1).
- **AC-I10** [auto] Values are stored with full precision as published; the app rounds to whole pesos.
- **AC-I11** [auto] Golden tests on saved fixtures — ECHING07 (con aguinaldo, con valor locativo, corrientes), Total país / Montevideo, rounded: Total 2016 = 58.072 / 69.557; Total 2023 = 96.230 / 118.532; Total 2025 = 110.097 / 133.145. ECHING09 (con aguinaldo, sin valor locativo): Total 2016 = 49.809 / 59.404. First quarter present: Enero–Marzo/16; ECHING07 Total país = 59.534 (rounded).

**Data quality checks** (failures stop the run unless marked warning)
- **AC-I12** [auto] All values > 0.
- **AC-I13** [auto] For the same territory, period and variant: per-capita < household income; with aguinaldo ≥ without; with valor locativo ≥ without.
- **AC-I14** [auto] For the same indicator and period: `interior` lies between `interior-5000` and `interior-menores`; `pais` lies between Montevideo and `interior`.
- **AC-I15** [auto] *(warning only)* The yearly total is within ±5 % of the mean of its four quarters (INE notes quarterly averages may fall slightly out of range).
- **AC-I16** [auto] Every year from 2016 to the last complete year has 4 quarters and 1 total; the current year has its published quarters only.
- **AC-I17** [auto] No income observation exists for departments other than 01 or for any level below departamento.

**Registry and notes**
- **AC-I18** [manual] `fuentes/ine_ech_ingresos_series.yml` documents: page, every file with code, title, URL and indicator mapping; periodicity; price bases; the regions; footnotes; the 2025 change to *ingreso disponible ajustado* (YDA) and whether the 2016– series are comparable across it (determined in F3.1 from INE material, not assumed); license and citation as published by INE. Maintainer decisions go in `notas_internas` (never rendered, AC-V19).
- **AC-I19** [auto] The weekly data workflow captures new versions of the income files automatically.

**App (applies once the region level exists)**
- **AC-I20** [manual] Topic "Ingresos" on the map: since there is no department data, the map shows the AC-M2/AC-V9 notice ("Los ingresos se publican por región: País · Montevideo · Interior") and, instead of a choropleth, a small comparison chart of País, Montevideo and the Interior regions for the selected indicator and period.
- **AC-I21** [manual] País, Montevideo and region fichas show the quarterly series since 2016 (line chart; yearly totals as a separate toggle), a selector for the variant (aguinaldo / valor locativo) and the price base (corrientes / enero 2005). The default variant is the one INE uses for its headline (decided in F3.1).
- **AC-I22** [auto] Department fichas other than Montevideo say "Ingresos: se publican para el Interior del país" and link to the `interior` ficha (AC-V24 pattern); segment, section, locality, barrio and CCZ fichas link to their department's region or to Montevideo.
- **AC-I23** [manual] Region fichas have no locator map; they show a sentence explaining the region ("Todos los departamentos salvo Montevideo; localidades de 5.000 o más habitantes") and links to País and Montevideo.
- **AC-I24** [manual] Next to income values the app shows: price base and period ("pesos corrientes por mes · jul–set 2026"), "Fuente: INE, ECH", that figures are subject to revision, and the YDA note when relevant.
- **AC-I25** [auto] CSV downloads include income rows with `tipo_periodo`, `periodo_inicio`, `periodo_fin` and the price base in the unit.
