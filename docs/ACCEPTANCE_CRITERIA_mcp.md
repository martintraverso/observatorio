# Observatorio Uruguay — Acceptance Criteria: MCP server (M13)

**Scope.** A local stdio MCP server that answers LLM questions with the observatory's published data. This file goes with `docs/PLAN_mcp.md`.

**Conventions.** Same as `docs/ACCEPTANCE_CRITERIA.md`:
- **[auto]** = automated test (pytest, on the fixture DuckDB that CI already builds);
- **[manual]** = checked by hand, with evidence in the PR.

The data rules in `docs/SYSTEM.md` §4 apply to every tool. Tool names, parameters and result keys are in Spanish (D-MCP.4).

**Decisions taken on 2026-11-27:** D-MCP.1 local stdio first; D-MCP.2 data from the release DuckDB; D-MCP.3 curated tools only, no free SQL; D-MCP.4 Spanish names and descriptions; D-MCP.5 package `servidor_mcp/`, command `observatorio-mcp`; D-MCP.6 MCP Python SDK approved; D-MCP.7 only active sources.

## Data in the release (MCP.1)

- **AC-MCP1** [auto] `observatorio.duckdb` has, for every indicator, the metadata the app reads from `indicadores.json`: `cuadro`, `corte`, `grupo`, `niveles` and `periodos` with data. It comes from the same functions as `web.py`. A test checks that, for every indicator, these values equal the ones in `indicadores.json`.
- **AC-MCP2** [auto] The view `v_publicadas` returns only observations of sources with `estado = 'activa'` (D-MCP.7). With a source «en preparación» in the fixture, none of its values appear.

## Package and data access (MCP.2)

- **AC-MCP3** [auto] `observatorio-mcp` starts a stdio server. The in-memory MCP client of the SDK lists every tool of this file, each with a Spanish description and a JSON schema, and the resource `observatorio://reglas`.
- **AC-MCP4** [auto] The server's `instructions` state, in at most 12 lines: what the data is (sources, years, levels), the four §4 rules, and that every number must be cited with its source and period.
- **AC-MCP5** [auto] Without `OBS_MCP_DB`, the first start downloads `observatorio.duckdb` from `releases/latest` into the user cache with its release tag. A later start uses the cache and checks for a newer release at most once every 24 h. Without network, the cache is used and the tools say which release they are on. Without network and without cache, the error says how to fix it. Tested with a fake HTTP server.
- **AC-MCP6** [auto] The database is opened read-only. No tool accepts SQL, a table name or a column name from the client.
- **AC-MCP7** [auto] `listar_fuentes` returns each active source with name, organismo, licence, page, frequency, latest capture (file, sha256, date) and the citation text to use.

## Search (MCP.3)

- **AC-MCP8** [auto] `buscar_territorios("paysandu")` returns `departamento/11` first. Search ignores accents and case, as `plegar` does in the app (`app/src/lib/busqueda.ts`). Each result has id, nivel, nombre, depto and padre.
- **AC-MCP9** [auto] `buscar_territorios` filters by `nivel` and `depto`, and returns at most 20 results with a `hay_mas` flag.
- **AC-MCP10** [auto] `buscar_indicadores` returns code, name, unit, topic, source, levels and periods with data, and `calculado` (es_derivado). Filters by `tema` and `nivel` (only indicators with data at that level).
- **AC-MCP11** [auto] Every list result is capped (default 20, maximum 100) and says how many more there are. No tool returns more than 100 rows or more than ~25 kB of text.

## Values and series (MCP.4)

- **AC-MCP12** [auto] `obtener_valores` returns each value with unit, period (label, start, end, type), level, territory name, `es_estimado`, `calculado`, `nota`, and `cita`: source, file, sha256, processing date and `captura_id`.
- **AC-MCP13** [auto] *(§4.4)* When an indicator has no value for a territory, the result says `sin_dato` with the reason ("no se publica por <nivel>", "sin dato para <periodo>") and lists the alternatives that do have it: the containing territories (padre chain and `pertenece_a`) and other levels of the same indicator. It never returns a value of another territory or level in place of the one asked for.
- **AC-MCP14** [auto] *(§4.1)* No tool returns a value that is not in `observaciones`. Test: for every value any tool returns over the fixture, the (indicador, territorio_id, periodo, valor) exists in `observaciones`. In particular, the population of a department is the published one, never the sum of its sections or segments.
- **AC-MCP15** [auto] *(§4.2)* Estimates and calculated rates are flagged in every result, and the formula of a calculated rate is returned with it.
- **AC-MCP16** [auto] `obtener_serie` returns the periods in order. Where the indicator has a `corte` (AC-E13/AC-E30), the series is split into separate segments with the reason, and the result says the values are not comparable across the cut.
- **AC-MCP17** [auto] Without `periodo`, the latest period with data is used and the result says which one. An unknown period, indicator or territory returns an error that names the search tool to use.

## Compare and summary (MCP.5)

- **AC-MCP18** [auto] `comparar(indicador, nivel, periodo?, dentro_de?)` returns every territory of that level that has a value, sorted, with rank, and the territories without a value listed apart. `dentro_de` limits it to the territories inside one department or region.
- **AC-MCP19** [auto] *(§4.1)* `comparar` shows a total for the country or the department only if the source publishes it as its own observation, labelled as such. It never computes a total, a mean or a share from the territories it lists.
- **AC-MCP20** [auto] Levels with more than 100 territories (segmento, localidad, sección) need `dentro_de` or return pages of 100 with the total count.
- **AC-MCP21** [auto] `resumen_territorio` returns the territory's parents, its topics, the latest value of each indicator the app's ficha shows first, the "Educación: datos por departamento" pattern below departamento (AC-E28), and the link to its ficha on the published site.

## Documentation and close (MCP.6)

- **AC-MCP22** [manual] `servidor_mcp/README.md` explains in Spanish how to install with `uvx`, configure Claude Desktop and Claude Code (`claude mcp add`), use other MCP clients, and where the cache lives. Following it on a clean machine works (evidence in the PR).
- **AC-MCP23** [manual] `docs/investigacion/mcp_preguntas.md` lists 15 questions covering every tool and every §4 rule (for example "¿Cuántas personas viven en la sección 3 de Flores?", "¿Cuál es la tasa de desempleo en Rivera?", "¿Qué departamento tiene la mayor tasa de promoción en primaria pública?", a question about a level that is not published). Each one has the expected answer and source. Asked to Claude with the server connected, at least 14 of 15 answers have the right number, period and source; no answer gives a number for a level that is not published.
- **AC-MCP24** [manual] SYSTEM.md has a section on the MCP server (tools, data source, rules), and the main README links to the install guide.
