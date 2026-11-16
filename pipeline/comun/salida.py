"""Escritura de las salidas: Parquet por tabla y una base DuckDB con todo."""

from __future__ import annotations

from pathlib import Path

import duckdb


def escribir_duckdb(salida: Path, tablas: list[str], geometria: dict[str, str] | None = None,
                    vistas: dict[str, str] | None = None) -> Path:
    """Crea `<salida>/observatorio.duckdb` desde `<salida>/<tabla>.parquet`.

    `geometria` = {tabla: columna_wkb}: la columna `geometry` del GeoParquet se guarda con ese nombre.
    `vistas` = {nombre: SELECT ...}.
    """
    db = Path(salida) / "observatorio.duckdb"
    db.unlink(missing_ok=True)
    geometria, vistas = geometria or {}, vistas or {}
    con = duckdb.connect(str(db))
    try:
        for t in tablas:
            origen = str(Path(salida) / f"{t}.parquet")
            if t in geometria:
                con.execute(f"CREATE TABLE {t} AS SELECT * EXCLUDE (geometry), geometry AS {geometria[t]} "
                            "FROM read_parquet(?)", [origen])
            else:
                con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_parquet(?)", [origen])
        for nombre, sql in vistas.items():
            con.execute(f"CREATE VIEW {nombre} AS {sql}")
    finally:
        con.close()
    return db
