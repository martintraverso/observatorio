# Observatorio Uruguay — Plan M13: MCP server (data for LLMs)

Read `docs/SYSTEM.md` (§4 data rules, §5 data model) and `docs/ACCEPTANCE_CRITERIA_mcp.md` (AC-MCP1…MCP24) first. One story per PR, and each PR lists its AC-MCP IDs. Stories are compatible with `/tomar-tarea` and `/trabajar`.

## Goal

Let an LLM (Claude Desktop, Claude Code or any other MCP client) answer questions about Uruguay with the observatory's data. Every number it gets keeps its unit, period, level, source and `captura_id`, and the server enforces the §4 rules so the LLM cannot invent a value at a level the source does not publish.

## Decisions taken (maintainer, 2026-11-27)

- **D-MCP.1 Local first.** A stdio server that each person runs on their own machine. No hosting, no cost, no new public service. A public HTTP endpoint is a later, separate milestone (it needs a host, a domain, rate limits and monitoring; CLAUDE.md requires the maintainer's OK for a new service).
- **D-MCP.2 Data from the release DuckDB.** The server downloads `observatorio.duckdb` from the latest data release once, keeps it in the user's cache, and refreshes it when a newer release exists. It opens it read-only.
- **D-MCP.3 Curated tools only.** A fixed set of tools; no free SQL. The server applies the §4 rules, so the LLM never sums values upward or fills a missing level.

- **D-MCP.4 Spanish.** Tool names, parameters, result keys and descriptions are in Spanish (`buscar_territorios`, `obtener_valores`…), as CLAUDE.md asks. The data (names, units, notes) is already Spanish.
- **D-MCP.5 Package and command.** A package in `servidor_mcp/` (not `mcp/`, which would shadow the SDK package), with its own `pyproject.toml` and the command `observatorio-mcp`. People install it with `uvx --from "git+https://github.com/martintraverso/observatorio#subdirectory=servidor_mcp" observatorio-mcp`. Its dependencies (official MCP Python SDK and `duckdb`) stay out of the pipeline's `requirements.txt`.
- **D-MCP.6 New dependency approved.** The official MCP Python SDK (`mcp` on PyPI).
- **D-MCP.7 Sources «en preparación» excluded**, as in the app (F2.5d). The release DuckDB holds every loaded source, so the server filters on `fuentes.estado = 'activa'`.

## Context (as of 2026-11-27, `main` at d2c4fad)

**What the release already has.** Each `datos-*` release publishes `observatorio.duckdb` (72 MB):
- `observaciones` (125,053 rows): indicador, territorio_id, periodo, periodo_inicio/fin, tipo_periodo (`anio`, `trimestre`, `trimestre_movil`, `censo`), valor, es_estimado, captura_id;
- `indicadores` (8,432): codigo, nombre, unidad, tema, columna_origen, fuente_id, nota, es_derivado, formula;
- `territorios` (5,539): id, nivel, codigo, nombre, depto, padre_id, area_km2, geom_wkb, over 10 levels (pais, region, departamento, municipio_mvd, ccz_mvd, barrio_mvd, seccion, localidad, segmento, area_especial);
- `capturas`, `fuentes` (licence, page, notes) and `correspondencias` (`pertenece_a`);
- the view `v_observaciones`, which joins each value with its territory, indicator and capture.

**What the release does not have.** `pipeline/web.py` computes some indicator metadata only for the app's `indicadores.json`: `cuadro` (MEC table code), `corte` (AC-E13/AC-E30 concept change in a series, from the source registry), `grupo` (education level) and the `niveles`/`periodos` with data. The MCP server needs the same facts. They go into the DuckDB in MCP.1, so the server and the app read one definition.

**Rules the tools must apply (SYSTEM.md §4).**
1. Values are returned at the level the source publishes. No tool sums, averages or otherwise derives a value for a larger territory. Example: departments sum to 3,495,947 people; sections and segments to 3,338,018.
2. Estimates (`es_estimado`) and observatory-calculated rates (`es_derivado`, "calculado por el observatorio") are flagged in every result.
3. Every value carries its `captura_id`, with file, sha256, processing date and the source's citation.
4. When an indicator has no value for the territory or level asked for, the tool says so and names the nearest levels or containing territories that do have it. It never substitutes one silently.

## Stories

### MCP.1 — Indicator metadata in the release (pipeline) · Alta · S
- Write the app's indicator metadata (`cuadro`, `corte`, `grupo`, levels and periods with data) to the DuckDB, from the same functions `web.py` uses (`con_cuadro`, `con_corte`, `con_mapa`, `disponibilidad`), as a table `indicadores_web` or extra columns. Add the view `v_publicadas` (only active sources).
- No change to §4 or to id formats. AC-MCP1, AC-MCP2.

### MCP.2 — Package, data download and first tool · Alta · M · blocked by MCP.1
- `servidor_mcp/` with `pyproject.toml`, the command, and the server `instructions` (what the data is, the §4 rules in four lines, how to cite).
- Data access: download `observatorio.duckdb` from `releases/latest`, keep it in the user cache (`$XDG_CACHE_HOME/observatorio-mcp/`) with the release tag, check for a newer release at most once a day, and keep working offline with the cached copy. `OBS_MCP_DB=/path` points to a local file (for development and tests).
- Tool `listar_fuentes`. Resource `observatorio://reglas` (rules and glossary).
- Tests run on the fixture DuckDB that `tests/conftest.py` already builds; one test speaks the MCP protocol end to end with the SDK's in-memory client. AC-MCP3…MCP7.

### MCP.3 — Search tools · Alta · M · blocked by MCP.2
- `buscar_territorios(texto, nivel?, depto?)`: same folding as the app (`plegar`: lower case, no accents), ranked like the app's search.
- `buscar_indicadores(texto, tema?, nivel?)`: name, unit, topic, source, levels and periods with data, `calculado`.
- AC-MCP8…MCP11.

### MCP.4 — Values and series with the data rules · Alta · M · blocked by MCP.3
- `obtener_valores(indicador, territorios, periodo?)` and `obtener_serie(indicador, territorio)`.
- Missing value → explicit `sin_dato` with the reason and the nearest alternatives (containing territories from `padre_id`/`correspondencias`, other levels with data). Concept changes (`corte`) split a series. Every value carries its citation.
- AC-MCP12…MCP17.

### MCP.5 — Compare, rank and territory summary · Media · M · blocked by MCP.4
- `comparar(indicador, nivel, periodo?, dentro_de?)`: every territory of one level, sorted, optionally inside one department. The country value is shown only if the source publishes it, never as a sum. Large levels (segmento: 4,538) need `dentro_de` or are paginated.
- `resumen_territorio(territorio)`: parents, topics, the latest value of the main indicators (as the app's ficha does) and the ficha's link on the published site.
- AC-MCP18…MCP21.

### MCP.6 — Install guide, sample questions and close · Media · S · blocked by MCP.5
- `servidor_mcp/README.md`: install with `uvx`, configuration for Claude Desktop and Claude Code (`claude mcp add`), other MCP clients, cache and offline behaviour.
- `docs/investigacion/mcp_preguntas.md`: 15 sample questions with the expected answer and source, checked by hand with a real client (evidence in the PR). Update SYSTEM.md (new section) and README.
- AC-MCP22…MCP24.

## Out of scope (later)

- Public HTTP endpoint (D-MCP.1): its own milestone, with hosting chosen by the maintainer.
- Geometry tools (point-in-polygon "¿en qué sección está esta dirección?"): needs a geocoder, which is a new service.
- An automated eval that runs an LLM over the sample questions (it costs API money on each run): only if the maintainer asks for it.
- Free SQL (D-MCP.3).
