"""Fase 0: carga las unidades geoestadísticas del Censo 2023 (INE).

Lee el zip (o la carpeta ya descomprimida) que publica el INE y genera:

  datos/salida/territorios.parquet      territorios de todos los niveles (GeoParquet)
  datos/salida/observaciones.parquet    conteos del Censo 2023 por territorio
  datos/salida/correspondencias.parquet relaciones entre territorios (segmento -> localidad)
  datos/salida/indicadores.parquet      catálogo de indicadores
  datos/salida/capturas.parquet         de qué archivo salió cada dato (con sha256)
  datos/salida/observatorio.duckdb      todo lo anterior en una base DuckDB
  datos/salida/web/<nivel>.geojson      geometrías simplificadas para la app
  datos/salida/reporte_validacion.md    controles de calidad

Uso:
  python pipeline/territorios_2023.py RUTA_AL_ZIP_O_CARPETA [--salida datos/salida] [--esperado ESPERADO.yml]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
import shapely
import yaml

VERSION_GEO = "INE-2023"
FUENTE_ID = "ine_unidades_geoestadisticas_2023"
PERIODO = "2023"

CAPAS = {
    "depto_23_pg": "departamento",
    "sc_23_pg": "seccion",
    "sg_23_pg": "segmento",
    "loc_23_pg": "localidad",
    "barrios_mvd_23_pg": "barrio_mvd",
    "ccz_mvd_23_pg": "ccz_mvd",
}

# Nombres con tildes (el geopackage los trae en mayúsculas y sin tildes).
NOMBRES_DEPTO = {
    "01": "Montevideo", "02": "Artigas", "03": "Canelones", "04": "Cerro Largo",
    "05": "Colonia", "06": "Durazno", "07": "Flores", "08": "Florida",
    "09": "Lavalleja", "10": "Maldonado", "11": "Paysandú", "12": "Río Negro",
    "13": "Rivera", "14": "Rocha", "15": "Salto", "16": "San José",
    "17": "Soriano", "18": "Tacuarembó", "19": "Treinta y Tres",
}

INDICADORES = [
    # codigo, columna INE, nombre, unidad
    ("pob_total", "POB_TOT_23", "Personas", "personas"),
    ("pob_hombres", "POB_TOT_HOM_23", "Hombres", "personas"),
    ("pob_mujeres", "POB_TOT_MUJ_23", "Mujeres", "personas"),
    ("viviendas_total", "VIV_TOT_23", "Viviendas", "viviendas"),
]

NOTA_INDICADORES = (
    "Censo 2023. Personas enumeradas por el operativo censal o por enumeración "
    "administrativa; no incluye personas en situación de calle. La enumeración "
    "administrativa se ubica a distintos niveles, por lo que la suma de unidades "
    "menores no coincide necesariamente con el total de la unidad mayor (INE, metadatos)."
)

TOLERANCIA_WEB = {  # grados; ~0.001 = 100 m
    "departamento": 0.002,
    "seccion": 0.0015,
    "segmento": 0.0004,
    "localidad": 0.0003,
    "barrio_mvd": 0.0002,
    "ccz_mvd": 0.0002,
}

MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y", "e", "a"}


def titulo(texto: str) -> str:
    """'VILLA GARCIA, MANGA RUR.' -> 'Villa Garcia, Manga Rur.' (sin inventar tildes)."""
    palabras = str(texto).strip().lower().split()
    salida = []
    for i, p in enumerate(palabras):
        salida.append(p if (i > 0 and p in MINUSCULAS) else p[:1].upper() + p[1:])
    return " ".join(salida)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def abrir_entrada(entrada: Path, tmp: Path) -> tuple[Path, str, str]:
    """Devuelve (carpeta con los .gpkg, sha256 del original, nombre del original)."""
    if entrada.is_file() and entrada.suffix.lower() == ".zip":
        with zipfile.ZipFile(entrada) as z:
            for m in z.infolist():
                destino = (tmp / m.filename).resolve()
                if not str(destino).startswith(str(tmp.resolve())):
                    raise ValueError(f"Ruta insegura dentro del zip: {m.filename}")
            z.extractall(tmp)
        carpeta = next((p.parent for p in tmp.rglob("depto_23_pg.gpkg")), None)
        if carpeta is None:
            raise FileNotFoundError("El zip no contiene depto_23_pg.gpkg")
        return carpeta, sha256(entrada), entrada.name
    if entrada.is_dir():
        h = hashlib.sha256()
        for capa in sorted(CAPAS):
            h.update(sha256(entrada / f"{capa}.gpkg").encode())
        return entrada, h.hexdigest(), entrada.name
    raise FileNotFoundError(f"No encuentro {entrada}")


def leer_capas(carpeta: Path) -> dict[str, gpd.GeoDataFrame]:
    capas = {}
    for archivo, nivel in CAPAS.items():
        gdf = gpd.read_file(carpeta / f"{archivo}.gpkg")
        if gdf.crs is None or gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)
        capas[nivel] = gdf
    return capas


def tid(nivel: str, codigo: str) -> str:
    return f"{VERSION_GEO}/{nivel}/{codigo}"


def construir_territorios(capas: dict[str, gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    filas = []

    def agregar(nivel, codigo, nombre, depto, padre, row, extra=None):
        filas.append({
            "id": tid(nivel, codigo), "nivel": nivel, "codigo": codigo, "nombre": nombre,
            "depto": depto, "padre_id": padre, "version_geo": VERSION_GEO,
            "area_km2": float(row["AREA_KM2"]), "geometry": row.geometry,
            **(extra or {}),
        })

    for _, r in capas["departamento"].iterrows():
        d = r["DEPTO"]
        if r["NOMDEPTO"] == "LIMITE CONTESTADO":
            agregar("area_especial", "02-limite-contestado", "Límite contestado (Artigas)", d,
                    tid("departamento", d), r, {"codigo_iso": r["CDEPTO_ISO"]})
        else:
            agregar("departamento", d, NOMBRES_DEPTO[d], d, None, r, {"codigo_iso": r["CDEPTO_ISO"]})

    for _, r in capas["seccion"].iterrows():
        agregar("seccion", r["CODSECC"], f"Sección {r['SECC']}", r["DEPTO"],
                tid("departamento", r["DEPTO"]), r)

    for _, r in capas["segmento"].iterrows():
        agregar("segmento", r["CODSEG"], f"Segmento {r['SEG']}", r["DEPTO"],
                tid("seccion", r["CODSECC"]), r)

    for _, r in capas["localidad"].iterrows():
        nombre = "Rural" if r["CODLOC"].endswith("900") else titulo(r["NOMLOC"])
        agregar("localidad", r["CODLOC"], nombre, r["DEPTO"], tid("departamento", r["DEPTO"]), r,
                {"codigo_iso": r["CLOC_ISO"]})

    for _, r in capas["barrio_mvd"].iterrows():
        agregar("barrio_mvd", str(r["CODBARRIOINE"]), titulo(r["NOMBARRIOINE"]), "01",
                tid("departamento", "01"), r)

    for _, r in capas["ccz_mvd"].iterrows():
        cod = str(r["CCZ"]).zfill(2)
        agregar("ccz_mvd", cod, f"CCZ {int(cod)} (Municipio {r['NOMMUNICIPIO']})", "01",
                tid("departamento", "01"), r)

    gdf = gpd.GeoDataFrame(filas, geometry="geometry", crs=4326)
    gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
    return gdf


def construir_observaciones(capas, territorios, captura_id) -> pd.DataFrame:
    claves = {
        "departamento": lambda r: r["DEPTO"],
        "seccion": lambda r: r["CODSECC"],
        "segmento": lambda r: r["CODSEG"],
        "localidad": lambda r: r["CODLOC"],
        "barrio_mvd": lambda r: str(r["CODBARRIOINE"]),
        "ccz_mvd": lambda r: str(r["CCZ"]).zfill(2),
    }
    filas = []
    for nivel, gdf in capas.items():
        for _, r in gdf.iterrows():
            if nivel == "departamento" and r["NOMDEPTO"] == "LIMITE CONTESTADO":
                continue  # repite los conteos de Artigas: no es un dato propio
            t = tid(nivel, claves[nivel](r))
            for codigo, col, _, _ in INDICADORES:
                filas.append({
                    "indicador": codigo, "territorio_id": t, "periodo": PERIODO,
                    "valor": float(r[col]), "es_estimado": False, "captura_id": captura_id,
                })
    obs = pd.DataFrame(filas)
    faltan = set(obs.territorio_id) - set(territorios.id)
    if faltan:
        raise ValueError(f"Observaciones sin territorio: {sorted(faltan)[:5]}")
    return obs


def construir_correspondencias(capas) -> pd.DataFrame:
    sg = capas["segmento"]
    return pd.DataFrame({
        "origen_id": [tid("segmento", c) for c in sg["CODSEG"]],
        "destino_id": [tid("localidad", c) for c in sg["CODLOC"]],
        "tipo": "pertenece_a", "peso": 1.0, "metodo": "atributo CODLOC del INE",
    })


ESPERADO_COMPLETO = Path(__file__).resolve().parent / "esperado" / "ine_2023_completo.yml"


def cargar_esperado(path: Path) -> dict:
    """Valores esperados para los controles (por defecto, los del paquete completo del INE)."""
    esperado = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    faltan = {"territorios_por_nivel", "departamentos_con_secciones"} - set(esperado)
    if faltan:
        raise ValueError(f"{path}: faltan claves {sorted(faltan)}")
    return esperado


def validar(capas, territorios, obs, esperado) -> tuple[list[dict], pd.DataFrame]:
    checks = []

    def chk(nombre, ok, detalle=""):
        checks.append({"control": nombre, "ok": bool(ok), "detalle": detalle})

    conteo = territorios.nivel.value_counts()
    for nivel, n in esperado["territorios_por_nivel"].items():
        chk(f"{n} territorios de nivel {nivel}", conteo.get(nivel, 0) == n, f"{conteo.get(nivel, 0)} encontrados")
    otros = set(conteo.index) - set(esperado["territorios_por_nivel"])
    chk("Ningún nivel inesperado", not otros, ", ".join(sorted(otros)))
    chk("IDs únicos", territorios.id.is_unique, f"{len(territorios)} territorios")
    chk("Geometrías válidas", territorios.geometry.is_valid.all(),
        f"{(~territorios.geometry.is_valid).sum()} inválidas")
    chk("Ninguna geometría vacía", (~territorios.geometry.is_empty).all())

    ids = set(territorios.id)
    padres = territorios.padre_id.dropna()
    chk("Todo padre existe", padres.isin(ids).all(), f"{(~padres.isin(ids)).sum()} sin padre")

    seg = territorios[territorios.nivel == "segmento"]
    prefijo_ok = (seg.codigo.str[:4] == seg.padre_id.str.split("/").str[-1]).all()
    chk("Código de segmento empieza con el de su sección", prefijo_ok)

    sc, sg = capas["seccion"], capas["segmento"]
    suma_sg = sg.groupby("CODSECC")[[c for _, c, _, _ in INDICADORES]].sum()
    dif = (suma_sg.reindex(sc.CODSECC).values != sc[[c for _, c, _, _ in INDICADORES]].values).any(axis=1).sum()
    chk("Suma de segmentos = sección (todos los conteos)", dif == 0, f"{dif} secciones distintas")

    hm = (obs.pivot_table(index="territorio_id", columns="indicador", values="valor"))
    chk("Hombres + mujeres = personas", ((hm.pob_hombres + hm.pob_mujeres) == hm.pob_total).all(),
        f"{((hm.pob_hombres + hm.pob_mujeres) != hm.pob_total).sum()} territorios no cuadran")

    # Comparación departamento vs suma de secciones (diferencia esperada, documentada por el INE)
    d = capas["departamento"]
    d = d[d.NOMDEPTO != "LIMITE CONTESTADO"].set_index("DEPTO")
    s = sc.groupby("DEPTO")[["POB_TOT_23", "VIV_TOT_23"]].sum()
    # Solo se comparan departamentos con secciones en la entrada; cuántos debe haber
    # lo dice el archivo de esperados (19 en el paquete completo).
    con_secciones = d.index.isin(s.index)
    chk(f"{esperado['departamentos_con_secciones']} departamentos con secciones",
        con_secciones.sum() == esperado["departamentos_con_secciones"],
        f"{con_secciones.sum()} con secciones; sin secciones: {', '.join(sorted(d.index[~con_secciones])) or '—'}")
    d = d[con_secciones]
    comp = pd.DataFrame({
        "departamento": [NOMBRES_DEPTO[k] for k in d.index],
        "personas_depto": d.POB_TOT_23.values,
        "personas_suma_secciones": s.reindex(d.index).POB_TOT_23.values,
        "viviendas_depto": d.VIV_TOT_23.values,
        "viviendas_suma_secciones": s.reindex(d.index).VIV_TOT_23.values,
    }, index=d.index).sort_index()
    comp["dif_personas"] = comp.personas_depto - comp.personas_suma_secciones
    comp["dif_personas_pct"] = (comp.dif_personas / comp.personas_depto * 100).round(1)
    chk("Viviendas: depto ≈ suma de secciones (±5)",
        (comp.viviendas_depto - comp.viviendas_suma_secciones).abs().max() <= 5,
        f"máx. diferencia {int((comp.viviendas_depto - comp.viviendas_suma_secciones).abs().max())}")
    return checks, comp


def exportar_web(territorios: gpd.GeoDataFrame, carpeta: Path) -> dict[str, int]:
    carpeta.mkdir(parents=True, exist_ok=True)
    tamanos = {}
    for nivel, tol in TOLERANCIA_WEB.items():
        g = territorios[territorios.nivel == nivel][["id", "codigo", "nombre", "depto", "padre_id", "geometry"]].copy()
        try:
            g["geometry"] = shapely.coverage_simplify(g.geometry.values, tol)
        except Exception:
            g["geometry"] = g.geometry.simplify(tol, preserve_topology=True)
        g["geometry"] = shapely.make_valid(shapely.set_precision(g.geometry.values, 1e-5))
        destino = carpeta / f"{nivel}.geojson"
        g.to_file(destino, driver="GeoJSON", layer_options={"COORDINATE_PRECISION": 5, "RFC7946": "YES"})
        tamanos[nivel] = destino.stat().st_size
    return tamanos


def escribir_reporte(path, checks, comp, territorios, obs, captura, tamanos):
    conteo = territorios.nivel.value_counts()
    lineas = [
        "# Reporte de validación — unidades geoestadísticas 2023",
        "",
        f"Archivo: `{captura['archivo']}` · sha256 `{captura['sha256'][:16]}…` · procesado {captura['fecha_proceso']}",
        "",
        "## Territorios cargados",
        "",
        "| Nivel | Cantidad |", "|---|---:|",
        *[f"| {n} | {conteo.get(n, 0)} |" for n in
          ["departamento", "seccion", "segmento", "localidad", "barrio_mvd", "ccz_mvd", "area_especial"]],
        "",
        f"Observaciones: {len(obs)} ({obs.indicador.nunique()} indicadores).",
        "",
        "## Controles",
        "",
        "| Control | Resultado | Detalle |", "|---|---|---|",
        *[f"| {c['control']} | {'OK' if c['ok'] else 'FALLA'} | {c['detalle']} |" for c in checks],
        "",
        "## Departamento vs. suma de secciones",
        "",
        "Diferencia esperada: el INE ubica parte de la enumeración administrativa solo a nivel de "
        "localidad o departamento. La app muestra siempre el valor publicado para cada nivel.",
        "",
        "| Código | Departamento | Personas (depto) | Personas (suma secciones) | Dif. | Dif. % | Viviendas (depto) | Viviendas (suma secc.) |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
        *[f"| {k} | {r.departamento} | {r.personas_depto:,} | {r.personas_suma_secciones:,} | {r.dif_personas:,} | {r.dif_personas_pct} | {r.viviendas_depto:,} | {r.viviendas_suma_secciones:,} |"
          .replace(",", ".") for k, r in comp.iterrows()],
        f"| | **Total** | {comp.personas_depto.sum():,} | {comp.personas_suma_secciones.sum():,} | {comp.dif_personas.sum():,} | | {comp.viviendas_depto.sum():,} | {comp.viviendas_suma_secciones.sum():,} |".replace(",", "."),
        "",
        "Nota: el total oficial del Censo 2023 (3.499.451) incluye a toda la población estimada; "
        "estas capas no incluyen a las personas en situación de calle.",
        "",
        "## Archivos para la app",
        "",
        "| Archivo | Tamaño |", "|---|---:|",
        *[f"| web/{n}.geojson | {t / 1e6:.1f} MB |" for n, t in tamanos.items()],
        "",
    ]
    Path(path).write_text("\n".join(lineas), encoding="utf-8")


def escribir_duckdb(salida: Path):
    db = salida / "observatorio.duckdb"
    if db.exists():
        db.unlink()
    con = duckdb.connect(str(db))
    def p(n: str) -> str:
        return str(salida / f"{n}.parquet")

    con.execute(f"CREATE TABLE territorios AS SELECT * EXCLUDE (geometry), geometry AS geom_wkb FROM read_parquet('{p('territorios')}')")
    for t in ["observaciones", "correspondencias", "indicadores", "capturas", "fuentes"]:
        con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_parquet('{p(t)}')")
    con.execute("""
        CREATE VIEW v_observaciones AS
        SELECT o.*, t.nivel, t.codigo, t.nombre AS territorio, t.depto,
               i.nombre AS indicador_nombre, i.unidad, c.fuente_id, c.fecha_proceso
        FROM observaciones o
        JOIN territorios t ON t.id = o.territorio_id
        JOIN indicadores i ON i.codigo = o.indicador
        JOIN capturas c ON c.id = o.captura_id
    """)
    con.close()
    return db


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path, help="zip del INE o carpeta con los .gpkg")
    ap.add_argument("--salida", type=Path, default=Path("datos/salida"))
    ap.add_argument("--esperado", type=Path, default=ESPERADO_COMPLETO,
                    help="yml con los valores esperados para los controles (por defecto, paquete completo)")
    args = ap.parse_args(argv)
    args.salida.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        carpeta, huella, nombre = abrir_entrada(args.entrada, Path(tmp))
        capas = leer_capas(carpeta)

    ahora = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    captura = {"id": f"{FUENTE_ID}:{huella[:12]}", "fuente_id": FUENTE_ID, "archivo": nombre,
               "sha256": huella, "fecha_proceso": ahora}

    territorios = construir_territorios(capas)
    obs = construir_observaciones(capas, territorios, captura["id"])
    corr = construir_correspondencias(capas)
    checks, comp = validar(capas, territorios, obs, cargar_esperado(args.esperado))

    territorios.to_parquet(args.salida / "territorios.parquet", index=False)
    obs.to_parquet(args.salida / "observaciones.parquet", index=False)
    corr.to_parquet(args.salida / "correspondencias.parquet", index=False)
    pd.DataFrame([{"codigo": c, "nombre": n, "unidad": u, "columna_origen": col,
                   "fuente_id": FUENTE_ID, "nota": NOTA_INDICADORES}
                  for c, col, n, u in INDICADORES]).to_parquet(args.salida / "indicadores.parquet", index=False)
    pd.DataFrame([captura]).to_parquet(args.salida / "capturas.parquet", index=False)
    pd.DataFrame([{"id": FUENTE_ID, "nombre": "Unidades geoestadísticas Censo 2023",
                   "organismo": "INE", "licencia": "Uso libre citando como fuente al INE",
                   "url": "https://www.gub.uy/instituto-nacional-estadistica/politicas-y-gestion/unidades-geostadisticas"}]
                 ).to_parquet(args.salida / "fuentes.parquet", index=False)
    escribir_duckdb(args.salida)
    tamanos = exportar_web(territorios, args.salida / "web")
    escribir_reporte(args.salida / "reporte_validacion.md", checks, comp, territorios, obs, captura, tamanos)

    fallas = [c for c in checks if not c["ok"]]
    print(json.dumps({"territorios": int(len(territorios)), "observaciones": int(len(obs)),
                      "controles_ok": len(checks) - len(fallas), "controles_falla": len(fallas)},
                     ensure_ascii=False))
    for c in fallas:
        print(f"FALLA: {c['control']} — {c['detalle']}", file=sys.stderr)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
