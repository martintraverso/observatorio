# Observatorio Uruguay
 
Before working, read:
1. `docs/System.md` — what the system is, the data rules (§4) and the app design (§8).
2. `docs/acceptance_criteria.md` — how each part is judged (AC IDs).
3. `docs/plan.md` — milestones in order. Work on the next unfinished one.
Rules:
- UI copy and identifiers in Spanish (Uruguay).
- Never aggregate population upward; store each value at the level its source publishes it.
- Every value keeps its `captura_id` (source file + sha256).
- Keep `pytest -q` green. Run the pipeline before data tests: `python pipeline/territorios_2023.py datos/crudo/Unidades_Geoestadisticas_Censo_2023.zip`.
- List satisfied AC IDs in every PR description.
- Ask the maintainer before adding services, changing id formats, deleting data or force-pushing.
 
