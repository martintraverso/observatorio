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


# ---------------------------------------------------------------- varias fuentes (F2.5c)
#
# Cada fuente escribe lo suyo en <salida>/fuentes/<fuente_id>/ (observaciones, capturas e indicadores).
# `combinar` arma con eso las tablas compartidas de <salida>/ y la base DuckDB, y controla que encajen.
# Los territorios y sus correspondencias son la geografía del Censo: los escribe su script en <salida>/.

COLUMNAS_OBSERVACION = ["indicador", "territorio_id", "periodo", "periodo_inicio", "periodo_fin", "tipo_periodo",
                        "valor", "es_estimado", "captura_id"]
COLUMNAS_INDICADOR = ["codigo", "nombre", "unidad", "tema", "columna_origen", "fuente_id", "nota", "es_derivado", "formula"]
VISTA_OBSERVACIONES = """
    SELECT o.*, t.nivel, t.codigo, t.nombre AS territorio, t.depto,
           i.nombre AS indicador_nombre, i.unidad, c.fuente_id, c.fecha_proceso
    FROM observaciones o
    JOIN territorios t ON t.id = o.territorio_id
    JOIN indicadores i ON i.codigo = o.indicador
    JOIN capturas c ON c.id = o.captura_id
"""


class ErrorCombinar(ValueError):
    pass


def completar_indicadores(indicadores):
    """`es_derivado` (bool) y `formula` (texto) del catálogo (F4.2, AC-E3): un valor publicado tal cual no es
    derivado y no tiene fórmula; una tasa que calcula el observatorio a partir de conteos publicados (decisión D2
    de F4) es derivada y dice su fórmula. Completa las salidas de fuentes escritas antes de F4.2."""
    ind = indicadores.copy()
    if "es_derivado" not in ind.columns:
        ind["es_derivado"] = False
    if "formula" not in ind.columns:
        ind["formula"] = ""
    ind["es_derivado"] = ind["es_derivado"].fillna(False).astype(bool)
    ind["formula"] = ind["formula"].fillna("").astype(str)
    return ind


def carpeta_fuente(salida: Path, fuente_id: str) -> Path:
    return Path(salida) / "fuentes" / fuente_id


def escribir_fuente(salida: Path, fuente_id: str, observaciones, capturas, indicadores) -> Path:
    """Guarda las tablas de una fuente en <salida>/fuentes/<fuente_id>/."""
    from comun.capturas import tabla_capturas

    d = carpeta_fuente(salida, fuente_id)
    d.mkdir(parents=True, exist_ok=True)
    faltan = [c for c in COLUMNAS_OBSERVACION if c not in observaciones.columns]
    if faltan:
        raise ErrorCombinar(f"{fuente_id}: a las observaciones les faltan columnas {faltan}")
    observaciones[COLUMNAS_OBSERVACION].to_parquet(d / "observaciones.parquet", index=False)
    tabla_capturas(capturas).to_parquet(d / "capturas.parquet", index=False)
    completar_indicadores(indicadores)[COLUMNAS_INDICADOR].to_parquet(d / "indicadores.parquet", index=False)
    return d


def reconstruir_carpetas(salida: Path) -> list[str]:
    """Si una fuente está en las tablas compartidas pero no tiene carpeta (p. ej. en Actions, donde se baja del
    release solo lo compartido y esa fuente dio «sin cambios»), su carpeta se arma separando esas tablas."""
    import pandas as pd

    salida = Path(salida)
    if not all((salida / f"{t}.parquet").exists() for t in ("observaciones", "capturas", "indicadores")):
        return []
    cap = pd.read_parquet(salida / "capturas.parquet")
    obs = pd.read_parquet(salida / "observaciones.parquet")
    ind = pd.read_parquet(salida / "indicadores.parquet")
    hechas = []
    for fuente_id, caps in cap.groupby("fuente_id"):
        if carpeta_fuente(salida, fuente_id).exists():
            continue
        escribir_fuente(salida, fuente_id, obs[obs.captura_id.isin(caps.id)], caps.to_dict("records"),
                        ind[ind.fuente_id == fuente_id])
        hechas.append(fuente_id)
    return hechas


def combinar(salida: Path, fuentes: dict[str, dict]) -> dict:
    """Tablas compartidas desde las carpetas de cada fuente, controles de encaje y base DuckDB."""
    import pandas as pd

    from comun.registro import tabla_fuentes

    salida = Path(salida)
    reconstruir_carpetas(salida)
    carpetas = sorted(p for p in (salida / "fuentes").glob("*") if p.is_dir())
    if not carpetas:
        raise ErrorCombinar(f"No hay salidas de fuentes en {salida / 'fuentes'}")
    desconocidas = [p.name for p in carpetas if p.name not in fuentes]
    if desconocidas:
        raise ErrorCombinar(f"Salidas de fuentes que no están en el registro: {desconocidas}")
    tablas = {t: pd.concat([pd.read_parquet(p / f"{t}.parquet") for p in carpetas], ignore_index=True)
              for t in ("observaciones", "capturas", "indicadores")}
    tablas["indicadores"] = completar_indicadores(tablas["indicadores"])
    obs, cap, ind = tablas["observaciones"], tablas["capturas"], tablas["indicadores"]
    territorios = pd.read_parquet(salida / "territorios.parquet", columns=["id"])

    errores = []
    if not ind.codigo.is_unique:
        errores.append(f"indicadores repetidos entre fuentes: {sorted(ind.codigo[ind.codigo.duplicated()])}")
    if not cap.id.is_unique:
        errores.append(f"capturas repetidas: {sorted(cap.id[cap.id.duplicated()])}")
    sin_captura = set(obs.captura_id) - set(cap.id)
    if sin_captura:
        errores.append(f"observaciones con captura_id que no está en capturas: {sorted(sin_captura)[:5]}")
    sin_territorio = set(obs.territorio_id) - set(territorios.id)
    if sin_territorio:
        errores.append(f"observaciones sin territorio: {sorted(sin_territorio)[:5]}")
    sin_indicador = set(obs.indicador) - set(ind.codigo)
    if sin_indicador:
        errores.append(f"observaciones de indicadores que no están en el catálogo: {sorted(sin_indicador)}")
    repetidas = obs.duplicated(["indicador", "territorio_id", "periodo"])
    if repetidas.any():
        errores.append(f"{int(repetidas.sum())} observaciones repetidas (mismo indicador, territorio y período)")
    if errores:
        raise ErrorCombinar("Las salidas de las fuentes no encajan:\n  " + "\n  ".join(errores))

    for t, df in tablas.items():
        df.to_parquet(salida / f"{t}.parquet", index=False)
    tabla_fuentes(fuentes).to_parquet(salida / "fuentes.parquet", index=False)
    escribir_duckdb(salida, ["territorios", "observaciones", "correspondencias", "indicadores", "capturas", "fuentes"],
                    geometria={"territorios": "geom_wkb"}, vistas={"v_observaciones": VISTA_OBSERVACIONES})
    return {"fuentes": [p.name for p in carpetas], "observaciones": len(obs), "capturas": len(cap)}
