# Observatorio Uruguay — Plan M11: Dynamic territorial levels on the map
 
Read `docs/SYSTEM.md` (§8, the app) and `docs/ACCEPTANCE_CRITERIA_niveles.md` (AC-N1…N13) first. One story per PR, and each PR lists its AC-N IDs. Stories are compatible with `/tomar-tarea` and `/trabajar`.
 
## Context (as of 2026-11-24, `main` at 9cc3f92)
 
What the code does today:
 
**Level list**
- `app/src/lib/mapa/estado.ts` hard-codes the map levels:
  - `NIVELES_MAPA = ['departamento', 'municipio_mvd', 'seccion', 'segmento']`;
  - their labels: `ETIQUETA_NIVEL_MAPA`, `OPCION_NIVEL_MAPA`;
  - the segment zoom: `ZOOM_SEGMENTOS = 9`.
- The selector in `app/src/routes/+page.svelte` lists `nivelesConDatos(data.indicadores)`. That is the union of the levels of **all** indicators, so it always shows the same 4.
**Notices**
- When the chosen indicator has no data at the chosen level, `avisoNivel()` shows the AC-M2 / AC-V9 notice ("«X» no se publica por …"), with buttons to the levels that do have data.
- The same notice carries the regional comparison for Ingresos (AC-I20).
**Map and selection**
- `Mapa.svelte` paints `NIVELES_MAPA`. The PMTiles already holds more layers (`pipeline/web.py` `PMTILES_MINZOOM`): departamento, area_especial, seccion, localidad, barrio_mvd, ccz_mvd, segmento (from zoom 9), pais and municipio_mvd.
- `elegirNivel()` reframes the map with level-specific code (municipio → Montevideo, AC-V7).
- `territorioEnNivel()` applies AC-V8, using the ficha's parents or the INE code prefix.
**Pipeline**
- `pipeline/web.py` `disponibilidad()` already writes `indicadores.json` with each indicator's `niveles` (computed from the observations) and `periodos`.
- The census indicators (Personas, Hombres, Mujeres, Viviendas…) also have values for localidad, barrio_mvd and ccz_mvd. A selector that only followed the data would therefore offer up to 7 levels for Personas. D1 decides which levels go on the map.
**Tests that depend on this**
- `estado.spec.ts`: NIVELES_MAPA, OPCION_NIVEL_MAPA, avisoNivel, nivelesConDatos.
- `e2e/mapa.e2e.ts`, `e2e/trabajo.e2e.ts`.
- `e2e/visual/calidad.visual.ts`, which uses `nivelesConDatos`.
- The AC-V1 checks with 3, 4 and 5 levels.
## Decisions for the maintainer (before M11.1)
 
- **D1 — Which levels can be drawn on the map.** Proposed:
  | Level | On the map | Reason |
  |---|---|---|
  | departamento, sección, segmento, municipio (Montevideo) | yes | as today |
  | barrio (Montevideo) | yes | needed by F5 (crime); gives Personas a level between municipio and segmento |
  | seccional policial | yes, when F5 loads it | F5 |
  | localidad | **no** | localities do not cover the country, so a choropleth leaves large blank areas |
  | CCZ | **no** | almost the same as municipio in Montevideo |
  Both stay searchable and keep their fichas.
  With D1, Personas offers: Departamento · Sección · Barrio · Segmento, plus Municipio if census values exist at that level (check in M11.1). If you want exactly "Departamento · Sección · Segmento", set barrio and municipio to "no" for census indicators, which needs a rule per topic. The proposal keeps one rule for everything: data + drawable.
- **D2 — Order, from coarse to fine:** Departamento · Municipio · Seccional · Sección · Barrio · Segmento. Montevideo has 8 municipios and 25 seccionales, so municipio goes first. Levels that only exist in Montevideo carry the help "Solo Montevideo".
- **D3 — What drives the selector.** The selected **indicator** drives it. A topic change selects the topic's first indicator (as today), and that indicator decides the levels. This is already in AC-N, recorded here so it is not reopened.
## Goal
 
The map's level selector offers only the levels where the selected indicator has data and that can be drawn, so the "no se publica por…" notice can no longer appear on the map. Adding a level (seccional in F5) needs no change to the app code.
 
**Order:**
- M11.1 first.
- M11.2 after M11.1. It can start with a fixture catalogue.
- M11.3 and M11.4 after M11.2.
- M11.5 last.
- F5 (crime) app work starts after M11.4.
## Stories
 
### M11.1 — Level catalogue in the pipeline
Criteria: AC-N1, AC-N2, AC-N3.
 
1. **Catalogue.** In `pipeline/web.py`, define `NIVELES_CATALOGO`: one entry per level, in the D2 order, with:
   - `id`;
   - `etiqueta`, and `ayuda` (optional);
   - `orden`;
   - `en_mapa` (D1);
   - `minzoom` (segmento: 9);
   - `ambito` (`pais` | `montevideo`), used for framing in M11.3.
2. **Single source of truth.** `PMTILES_MINZOOM` and `GEOJSON` must agree with it. Either derive them from the catalogue, or add a test that fails if a level with `en_mapa = true` has no PMTiles layer.
3. **Output.** Write the catalogue to `indicadores.json` as a top-level block (`{"niveles": [...], "indicadores": [...]}`), or as a separate `niveles.json`. Choose one and document it in `docs/SYSTEM.md` §8. If the file's shape changes, update every reader: app, e2e and visual tests.
4. **Indicator levels.** `disponibilidad()` keeps `niveles` per indicator, computed from the observations. Add tests:
   - a level with no observation for an indicator is not listed;
   - `pais` and `region` are listed (the fichas use them) but are `en_mapa = false` in the catalogue.
5. **Barrio values.** `valores/barrio_mvd.json` must exist for barrio, since it goes on the map. Check that `valores_por_nivel()` writes it.
Done when `indicadores.json` (or `niveles.json`) carries the catalogue, and the pipeline tests cover AC-N1–N3.
 
### M11.2 — Selector logic in `estado.ts`
Criteria: AC-N4, AC-N5, AC-N7, AC-N8, AC-N13.
 
1. **Remove the hard-coded levels.**
   - Remove `NIVELES_MAPA`, `ETIQUETA_NIVEL_MAPA` and `OPCION_NIVEL_MAPA`; `NivelMapa` becomes `string`.
   - Replace `ZOOM_SEGMENTOS` with the catalogue's `minzoom`. `LocalizadorCerca.svelte` uses it too.
2. **Add pure functions:**
   - `nivelesOfrecidos(indicador, catalogo)`: the levels with data and `en_mapa`, in catalogue order (AC-N4).
   - `nivelAlCambiar(actual, ofrecidos, catalogo)`: keep the current level if offered; otherwise the nearest coarser offered level, skipping `ambito = montevideo` levels unless the current level is also Montevideo-only; otherwise the coarsest offered level (AC-N7). Returns null when nothing is offered.
3. **URL.** `leerEstado()` validates `nivel` against `nivelesOfrecidos()` of the URL's indicator and applies `nivelAlCambiar()` (AC-N8).
4. **Old functions.**
   - `avisoNivel()` stays only for fichas (AC-V24), or is moved to the ficha code.
   - `nivelesConDatos()` is deleted.
   - `hastaDonde()` in `+page.svelte` uses the catalogue labels.
5. **Tests in `estado.spec.ts`:**
   - the AC-N5 table, using the real `build/datos-web/indicadores.json` where the test already reads it, and fixtures otherwise;
   - the three AC-N7 transitions;
   - an old URL with an unavailable level (AC-N8);
   - a fake level in a fixture catalogue appearing with no code change (AC-N13).
   Update or remove the tests that assert the old notice on the map.
### M11.3 — Map rendering and framing driven by the catalogue
Criteria: AC-N4 (map side), AC-N13; keep AC-V7 and AC-V8.
 
1. **Layers.** `Mapa.svelte` adds a choropleth layer for every catalogue level with `en_mapa = true`, with `minzoom` from the catalogue. `NIVELES_SELECCION` is built from the catalogue plus the selectable-only levels (localidad, ccz_mvd, area_especial).
2. **Framing (AC-V7) by `ambito`.** `elegirNivel()` uses `ambito` instead of level-specific code:
   - `montevideo`: fit to Montevideo;
   - `pais` (departamento, seccional): fit to the country;
   - other `pais` levels: fit to the selected department, if any;
   - a level with `minzoom`: at least that zoom.
3. **Selection (AC-V8).** `territorioEnNivel()` relies on the ficha's `padres` for every level. The INE code-prefix shortcut stays only for seccion and segmento → departamento. Barrio → municipio and segmento → barrio come from `padres` or `correspondencias`. When no parent is known, the selection is cleared (as today).
4. **Barrio.** Barrio is drawn with the same choropleth classes and legend as the other levels. Check it at 1440 and 390.
### M11.4 — Selector UI and removal of the map notice
Criteria: AC-N6, AC-N9, AC-N10, AC-N11.
 
1. **Options.** The "Nivel territorial" fieldset lists `nivelesOfrecidos(indicador)`. It keeps the vertical list (AC-V1).
   - With 1 level: static text "Nivel: Departamento", not a control.
   - With 0 levels (Ingresos): the fieldset is hidden.
2. **Changing indicator or topic.** `elegirIndicador()` and the topic change call `nivelAlCambiar()`. If the level changed, they call `elegirNivel()` (framing and AC-V8) and announce "Nivel: Departamento" in a polite live region.
3. **Notices.**
   - The `avisos` block no longer renders the "no se publica por…" message or its buttons.
   - The regional case (AC-I20) keeps its notice and `ComparacionRegional`, now triggered by "no drawable level and the indicator has `region`".
   - The segment zoom notice ("Acercá el mapa…") stays.
4. **AC-V1.** Extend the test to 1, 2, 5 and 6 options, at the four viewports. AC-V3 (no layout shift) is checked while switching between indicators that offer 1 and 5 levels.
5. **E2E.** Update `mapa.e2e.ts` and `trabajo.e2e.ts`:
   - Personas on Segmento → Tasa de desempleo gives Departamento, with no notice visible;
   - Ingresos hides the selector and shows the comparison;
   - a link `?indicador=tasa_desempleo&nivel=seccion` opens on Departamento and rewrites the URL.
### M11.5 — Visual check and documentation
Criteria: AC-N12; documentation.
 
- **Visual tests.** `e2e/visual/calidad.visual.ts` iterates over `nivelesOfrecidos()` per indicator instead of `nivelesConDatos()`. Update the snapshots in `capturas.visual.ts`.
- **Screenshots in the PR**, at 1440 and 390: Población, Trabajo, Educación and Ingresos, showing their levels and no notice. Seguridad is added to this list in F5.
- **`docs/SYSTEM.md` §8.** Document the level catalogue, the "data + drawable" rule, the AC-N7 fallback, and that the AC-M2 / AC-V9 notice now applies only to fichas.
- **`docs/ACCEPTANCE_CRITERIA.md` and `_UI.md`.** Annotate AC-M2 and AC-V9 with "superseded on the map by AC-N4/AC-N9 (M11); still applies to fichas". Do not delete them.
## Effect on F5 (crime)
F5 adds `seccional_policial` to the catalogue (`en_mapa = true`, `ambito = pais`, D2 order) and a PMTiles layer. Then:
- homicides offer Departamento · Seccional;
- the other crimes offer Departamento · Seccional · Barrio.
None of this changes the selector code (AC-N13). F5's AC-C24 depends on M11.4.
 