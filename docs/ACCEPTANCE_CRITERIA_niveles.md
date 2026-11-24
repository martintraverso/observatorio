# Observatorio Uruguay — Acceptance Criteria: Dynamic territorial levels on the map (M11)
 
**Scope.** Today the map's level selector always offers the same four levels (departamento, municipio, sección, segmento), taken from every indicator together (`nivelesConDatos`). Choosing a level where the selected indicator has no data shows the AC-M2/AC-V9 notice.
 
The goal: the selector offers **only the levels where the selected indicator has data and that can be drawn**, so the notice can no longer appear on the map.
 
Requested by the maintainer on 2026-11-23. Examples:
- "Personas" → Departamento · Sección · Segmento.
- Trabajo → Departamento · Municipio.
- Seguridad → Departamento · Seccional · Barrio.
**Conventions.** Same as `docs/ACCEPTANCE_CRITERIA.md`:
- **[auto]** = automated test;
- **[manual]** = checked by hand, with screenshots at 1440×900 and 390×844 in the PR.
AC-V* still apply, especially AC-V2 (level labels), AC-V3 (no layout shift) and AC-V8 (selection rule when changing level).
 
**What decides the levels: the indicator, not only the topic.** A topic's indicators can be published at different levels; for example, crime has no barrio for homicides. The selector follows the **selected indicator**. When the topic changes, its default indicator decides.
 
**Level catalogue**
- **AC-N1** [auto] The pipeline writes a level catalogue (`niveles.json`, or a `niveles` block in `indicadores.json`). Each level has:
  - id;
  - label and optional help (e.g. "Municipio" / "Solo Montevideo"; "Barrio" / "Solo Montevideo"; "Seccional" / "Seccional policial");
  - order, from coarse to fine;
  - `dibujable`: true when the level has a layer in the PMTiles;
  - minimum zoom, if any.
  The app reads this catalogue: `NIVELES_MAPA` and `OPCION_NIVEL_MAPA` are no longer hard-coded.
- **AC-N2** [auto] For every indicator, `indicadores.json` lists the levels where it has observations. The pipeline computes that list from the database; nobody writes it by hand. A level appears only if at least one territory of that level has a value in some period.
- **AC-N3** [auto] Levels without geometry (`pais`, `region`) are never offered in the selector.
**Selector**
- **AC-N4** [auto] The selector shows exactly the levels that both have data for the selected indicator (AC-N2) and are drawable (AC-N1), in catalogue order.
  - No option is disabled.
  - No option leads to a level without data.
- **AC-N5** [auto] Tests with the real `indicadores.json`, using the indicators loaded at merge time and extending the table as topics are added:
  | Indicator | Levels offered |
  |---|---|
  | Personas (Población) | Departamento · Sección · Segmento, plus Localidad / Barrio / CCZ if they have data and a layer |
  | Tasa de desempleo | Departamento · Municipio |
  | Any education indicator by department (e.g. matrícula de primaria común) | Departamento |
  | Tasa de homicidios (F5) | Departamento · Seccional |
  | Tasa de rapiñas (F5) | Departamento · Seccional · Barrio |
- **AC-N6** [manual] With a single level, the selector shows it as a static text ("Nivel: Departamento") instead of a one-option control. With no drawable level (Ingresos: país and región only), the selector is hidden and the topic keeps its own display (AC-I20 comparison chart).
**Changing topic, indicator or URL**
- **AC-N7** [auto] When the topic or indicator changes:
  - the current level is kept if it is offered;
  - otherwise the map moves to the nearest coarser level that is offered;
  - if no coarser level is offered, it moves to the coarsest level offered.
  No notice is shown. The selected territory follows AC-V8, and the map reframes as in AC-V7. Tests:
  - Personas / Segmento → Trabajo gives Departamento;
  - Trabajo / Municipio → Personas gives Departamento;
  - Rapiñas / Barrio → Homicidios gives Departamento.
- **AC-N8** [auto] A URL whose `nivel` is not offered for its `indicador` (an old link, or one typed by hand) opens with the AC-N7 rule. The URL is rewritten with `history.replaceState`, and no notice is shown.
- **AC-N9** [auto] No combination of indicator and level reachable from the map UI shows the AC-M2/AC-V9 "no se publica por…" notice.
  - The notice code stays for fichas only (AC-V24 still applies there).
  - The AC-M2 and AC-V9 tests are updated to state that the map never reaches that state.
  - Topics with only national or regional data keep their own explanatory notice (AC-I20).
**Layout and accessibility**
- **AC-N10** [auto] Changing the number of options (from 1 to 6) does not move any control above the selector, and the panel width does not change (AC-V3). At 390 px, the options wrap onto a second line or scroll inside the control. The page never scrolls sideways.
- **AC-N11** [auto] The selector is a radio group named "Nivel territorial". It works with the keyboard (arrow keys, Tab). The chosen level is announced when it changes automatically (AC-N7), through a polite live region.
- **AC-N12** [manual] Screenshots at 1440 and 390 for Población, Trabajo, Educación, Ingresos and (after F5) Seguridad show the levels of AC-N5 and no notice.
**Extensibility**
- **AC-N13** [auto] Adding a source with a new drawable level needs only pipeline changes (catalogue plus PMTiles layer); the selector code stays the same. Test: a fixture indicator at a fake drawable level appears in the selector without any app change.
 