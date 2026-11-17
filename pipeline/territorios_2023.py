"""Fase 0: carga las unidades geoestadísticas del Censo 2023 (INE).

Lee el zip (o la carpeta ya descomprimida) que publica el INE y genera:

  datos/salida/territorios.parquet          territorios de todos los niveles (GeoParquet)
  datos/salida/observaciones.parquet        conteos del Censo 2023 por territorio
  datos/salida/correspondencias.parquet     relaciones entre territorios (segmento -> localidad,
                                            CCZ -> municipio, departamento -> país)
  datos/salida/indicadores.parquet          catálogo de indicadores
  datos/salida/capturas.parquet             de qué archivo salió cada dato (con sha256)
  datos/salida/capturas_historial.parquet   una fila por corrida (nuevo / reprocesado / sin cambios / error)
  datos/salida/fuentes.parquet              registro de fuentes (todos los fuentes/*.yml)
  datos/salida/observatorio.duckdb          todo lo anterior en una base DuckDB
  datos/salida/reporte_validacion.md        controles de calidad

Los archivos para la app (datos/salida/web/) los arma después pipeline/web.py.

Si el sha256 del original es el de la última captura procesada y las salidas
están completas, no se reprocesa: la corrida queda como "sin cambios" (usar
--forzar para reprocesar igual).

Uso:
  python pipeline/territorios_2023.py RUTA_AL_ZIP_O_CARPETA [--salida datos/salida]
      [--esperado ESPERADO.yml] [--fuentes fuentes/] [--forzar]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
import yaml

from comun.capturas import Historial, ahora, nueva_captura
from comun.controles import Controles
from comun.entrada import carpeta_con, extraer_zip
from comun.huella import huella_entrada
from comun.periodos import TIPOS_PERIODO, censo
from comun.registro import cargar_fuentes, tabla_fuentes
from comun.salida import escribir_duckdb

RAIZ = Path(__file__).resolve().parents[1]
ESPERADO_COMPLETO = RAIZ / "pipeline" / "esperado" / "ine_2023_completo.yml"

VERSION_GEO = "INE-2023"
FUENTE_ID = "ine_unidades_geoestadisticas_2023"
PERIODO = censo(2023)  # tipo_periodo = censo, 2023-01-01, etiqueta "2023" (AC-L11)

CAPAS = {
    "depto_23_pg": "departamento",
    "sc_23_pg": "seccion",
    "sg_23_pg": "segmento",
    "loc_23_pg": "localidad",
    "barrios_mvd_23_pg": "barrio_mvd",
    "ccz_mvd_23_pg": "ccz_mvd",
}

# Salidas que tienen que existir para dar una corrida por "sin cambios".
SALIDAS = ["territorios.parquet", "observaciones.parquet", "correspondencias.parquet", "indicadores.parquet",
           "capturas.parquet", "fuentes.parquet", "observatorio.duckdb", "reporte_validacion.md"]

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

# Tema de cada indicador (los temas de la app: Población, Vivienda, Hogares, Trabajo, Ingresos, Educación).
TEMA = {"pob_total": "Población", "pob_hombres": "Población", "pob_mujeres": "Población",
        "viviendas_total": "Vivienda"}

NOTA_INDICADORES = (
    "Censo 2023. Personas enumeradas por el operativo censal o por enumeración "
    "administrativa; no incluye personas en situación de calle. La enumeración "
    "administrativa se ubica a distintos niveles, por lo que la suma de unidades "
    "menores no coincide necesariamente con el total de la unidad mayor (INE, metadatos)."
)

MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y", "e", "a"}

LINEA_CORRIDA = "Última corrida:"


def titulo(texto: str) -> str:
    """'VILLA GARCIA, MANGA RUR.' -> 'Villa Garcia, Manga Rur.' (sin inventar tildes)."""
    palabras = str(texto).strip().lower().split()
    salida = []
    for i, p in enumerate(palabras):
        salida.append(p if (i > 0 and p in MINUSCULAS) else p[:1].upper() + p[1:])
    return " ".join(salida)


def abrir_entrada(entrada: Path, tmp: Path) -> Path:
    """Carpeta con los .gpkg: el zip extraído en `tmp`, o la carpeta dada."""
    if entrada.is_file() and entrada.suffix.lower() == ".zip":
        return carpeta_con(extraer_zip(entrada, tmp), "depto_23_pg.gpkg")
    if entrada.is_dir():
        return entrada
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
    return pd.concat([gdf, construir_derivados(gdf, capas)], ignore_index=True)


def municipio_de_ccz(capas) -> dict[str, str]:
    """Código de CCZ ('01') -> letra del municipio ('CH'), del atributo NOMMUNICIPIO del INE."""
    return {str(r["CCZ"]).zfill(2): str(r["NOMMUNICIPIO"]).strip() for _, r in capas["ccz_mvd"].iterrows()}


# Lambert acimutal de áreas iguales centrada en Uruguay, para medir superficies.
PROYECCION_AREAS = "+proj=laea +lat_0=-32.5 +lon_0=-56 +datum=WGS84 +units=m"


def area_km2(geom, crs) -> float:
    return float(gpd.GeoSeries([geom], crs=crs).to_crs(PROYECCION_AREAS).area.iloc[0]) / 1e6


def construir_derivados(territorios: gpd.GeoDataFrame, capas) -> gpd.GeoDataFrame:
    """Niveles que el INE no publica como capa propia (F2.3), armados uniendo geometrías.

    - pais: INE-2023/pais/UY, unión de los departamentos (sin el área especial), para los totales
      nacionales que publica el INE (AC-L28).
    - municipio_mvd: INE-2023/municipio_mvd/<letra>, unión de los CCZ de cada municipio (AC-L17).
    Solo se unen geometrías: ningún valor se suma hacia arriba (SYSTEM.md §4). La superficie se mide
    sobre la geometría unida (proyección de áreas iguales), no se suma la de las partes: el AREA_KM2
    de la capa de CCZ del INE no está en km² (es unas 100 veces el área real).
    """
    def fila(nivel, codigo, nombre, depto, padre, partes, extra=None):
        geom = shapely.make_valid(shapely.union_all(partes.geometry.values))
        return {"id": tid(nivel, codigo), "nivel": nivel, "codigo": codigo, "nombre": nombre, "depto": depto,
                "padre_id": padre, "version_geo": VERSION_GEO, "area_km2": area_km2(geom, territorios.crs),
                "geometry": geom, **(extra or {})}

    filas = []
    deptos = territorios[territorios.nivel == "departamento"]
    if not deptos.empty:
        filas.append(fila("pais", "UY", "Uruguay", "", None, deptos, {"codigo_iso": "UY"}))
    ccz = territorios[territorios.nivel == "ccz_mvd"]
    letra = ccz.codigo.map(municipio_de_ccz(capas))
    for m, partes in ccz.groupby(letra):
        filas.append(fila("municipio_mvd", m, f"Municipio {m}", "01", tid("departamento", "01"), partes))
    return gpd.GeoDataFrame(filas, columns=territorios.columns, geometry="geometry", crs=territorios.crs)


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
                    "indicador": codigo, "territorio_id": t, **PERIODO.columnas(),
                    "valor": float(r[col]), "es_estimado": False, "captura_id": captura_id,
                })
    obs = pd.DataFrame(filas)
    faltan = set(obs.territorio_id) - set(territorios.id)
    if faltan:
        raise ValueError(f"Observaciones sin territorio: {sorted(faltan)[:5]}")
    return obs


def construir_correspondencias(capas) -> pd.DataFrame:
    sg = capas["segmento"]
    segmentos = pd.DataFrame({
        "origen_id": [tid("segmento", c) for c in sg["CODSEG"]],
        "destino_id": [tid("localidad", c) for c in sg["CODLOC"]],
        "tipo": "pertenece_a", "peso": 1.0, "metodo": "atributo CODLOC del INE",
    })
    mun = municipio_de_ccz(capas)
    ccz = pd.DataFrame({  # AC-L18
        "origen_id": [tid("ccz_mvd", c) for c in mun],
        "destino_id": [tid("municipio_mvd", m) for m in mun.values()],
        "tipo": "pertenece_a", "peso": 1.0, "metodo": "disolución de CCZ por NOMMUNICIPIO",
    })
    d = capas["departamento"]
    deptos = sorted(d.loc[d.NOMDEPTO != "LIMITE CONTESTADO", "DEPTO"])
    pais = pd.DataFrame({
        "origen_id": [tid("departamento", c) for c in deptos],
        "destino_id": tid("pais", "UY"),
        "tipo": "pertenece_a", "peso": 1.0, "metodo": "los departamentos forman el país",
    })
    return pd.concat([segmentos, ccz, pais], ignore_index=True)


def cargar_esperado(path: Path) -> dict:
    """Valores esperados para los controles (por defecto, los del paquete completo del INE)."""
    esperado = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    faltan = {"territorios_por_nivel", "departamentos_con_secciones"} - set(esperado)
    if faltan:
        raise ValueError(f"{path}: faltan claves {sorted(faltan)}")
    return esperado


def validar(capas, territorios, obs, esperado, niveles_publicados) -> tuple[Controles, pd.DataFrame]:
    c = Controles()

    conteo = territorios.nivel.value_counts()
    for nivel, n in esperado["territorios_por_nivel"].items():
        c.chk(f"{n} territorios de nivel {nivel}", conteo.get(nivel, 0) == n, f"{conteo.get(nivel, 0)} encontrados")
    otros = set(conteo.index) - set(esperado["territorios_por_nivel"])
    c.chk("Ningún nivel inesperado", not otros, ", ".join(sorted(otros)))
    c.chk("IDs únicos", territorios.id.is_unique, f"{len(territorios)} territorios")
    c.chk("Geometrías válidas", territorios.geometry.is_valid.all(),
          f"{(~territorios.geometry.is_valid).sum()} inválidas")
    c.chk("Ninguna geometría vacía", (~territorios.geometry.is_empty).all())

    ids = set(territorios.id)
    padres = territorios.padre_id.dropna()
    c.chk("Todo padre existe", padres.isin(ids).all(), f"{(~padres.isin(ids)).sum()} sin padre")

    mun = municipio_de_ccz(capas)
    ccz = territorios.loc[territorios.nivel == "ccz_mvd", "codigo"]
    sin = sorted(set(ccz) - {k for k, v in mun.items() if v in {"A", "B", "C", "CH", "D", "E", "F", "G"}})
    c.chk("Cada CCZ tiene municipio (A, B, C, CH, D, E, F, G)", not sin,
          f"sin municipio válido: {', '.join(sin)}" if sin else ", ".join(sorted(set(mun.values()))))

    seg = territorios[territorios.nivel == "segmento"]
    prefijo_ok = (seg.codigo.str[:4] == seg.padre_id.str.split("/").str[-1]).all()
    c.chk("Código de segmento empieza con el de su sección", prefijo_ok)

    sc, sg = capas["seccion"], capas["segmento"]
    suma_sg = sg.groupby("CODSECC")[[col for _, col, _, _ in INDICADORES]].sum()
    dif = (suma_sg.reindex(sc.CODSECC).values != sc[[col for _, col, _, _ in INDICADORES]].values).any(axis=1).sum()
    c.chk("Suma de segmentos = sección (todos los conteos)", dif == 0, f"{dif} secciones distintas")

    hm = (obs.pivot_table(index="territorio_id", columns="indicador", values="valor"))
    c.chk("Hombres + mujeres = personas", ((hm.pob_hombres + hm.pob_mujeres) == hm.pob_total).all(),
          f"{((hm.pob_hombres + hm.pob_mujeres) != hm.pob_total).sum()} territorios no cuadran")

    # AC-L10 (esquema): fechas presentes, tipo de período conocido e inicio <= fin.
    sin_fecha = obs.periodo_inicio.isna() | obs.periodo_fin.isna()
    con_fecha = obs[~sin_fecha]
    malos = obs[sin_fecha | ~obs.tipo_periodo.isin(TIPOS_PERIODO)]
    malos = pd.concat([malos, con_fecha[con_fecha.periodo_inicio > con_fecha.periodo_fin]])
    c.chk("Períodos válidos (fechas presentes, tipo conocido, inicio ≤ fin)", malos.empty, f"{len(malos)} observaciones con período inválido")

    # AC-P5: solo se guardan observaciones en los niveles que publica la fuente, salvo estimaciones.
    nivel_obs = obs.territorio_id.map(territorios.set_index("id").nivel)
    fuera = obs[~nivel_obs.isin(niveles_publicados) & ~obs.es_estimado]
    c.chk("Observaciones solo en niveles publicados por la fuente", fuera.empty,
          f"{len(fuera)} fuera de nivel ({', '.join(sorted(nivel_obs[fuera.index].unique()))})" if len(fuera)
          else f"niveles: {', '.join(sorted(nivel_obs.unique()))}")

    # Comparación departamento vs suma de secciones (diferencia esperada, documentada por el INE)
    d = capas["departamento"]
    d = d[d.NOMDEPTO != "LIMITE CONTESTADO"].set_index("DEPTO")
    s = sc.groupby("DEPTO")[["POB_TOT_23", "VIV_TOT_23"]].sum()
    # Solo se comparan departamentos con secciones en la entrada; cuántos debe haber
    # lo dice el archivo de esperados (19 en el paquete completo).
    con_secciones = d.index.isin(s.index)
    c.chk(f"{esperado['departamentos_con_secciones']} departamentos con secciones",
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
    c.chk("Viviendas: depto ≈ suma de secciones (±5)",
          (comp.viviendas_depto - comp.viviendas_suma_secciones).abs().max() <= 5,
          f"máx. diferencia {int((comp.viviendas_depto - comp.viviendas_suma_secciones).abs().max())}")
    return c, comp


def linea_corrida(fecha: str, resultado: str) -> str:
    return f"{LINEA_CORRIDA} {fecha} · {resultado}"


def escribir_reporte(path, controles, comp, territorios, obs, captura, resultado):
    conteo = territorios.nivel.value_counts()
    lineas = [
        "# Reporte de validación — unidades geoestadísticas 2023",
        "",
        f"Archivo: `{captura['archivo']}` · sha256 `{captura['sha256'][:16]}…` · procesado {captura['fecha_proceso']}",
        "",
        linea_corrida(captura["fecha_proceso"], resultado),
        "",
        "## Territorios cargados",
        "",
        "| Nivel | Cantidad |", "|---|---:|",
        *[f"| {n} | {conteo.get(n, 0)} |" for n in
          ["pais", "departamento", "seccion", "segmento", "localidad", "barrio_mvd", "municipio_mvd", "ccz_mvd",
           "area_especial"]],
        "",
        f"Observaciones: {len(obs)} ({obs.indicador.nunique()} indicadores).",
        "",
        "## Controles",
        "",
        *controles.tabla_md(),
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
    ]
    Path(path).write_text("\n".join(lineas), encoding="utf-8")


def marcar_reporte(path: Path, fecha: str, resultado: str) -> None:
    """Actualiza la línea 'Última corrida' de un reporte existente (corridas sin cambios)."""
    texto = path.read_text(encoding="utf-8")
    patron = re.compile(rf"^{re.escape(LINEA_CORRIDA)} .*$", re.MULTILINE)
    nuevo, n = patron.subn(linea_corrida(fecha, resultado), texto, count=1)
    if n == 0:  # reporte de una versión anterior, sin la línea
        nuevo = texto.replace("\n\n", f"\n\n{linea_corrida(fecha, resultado)}\n\n", 1)
    path.write_text(nuevo, encoding="utf-8")


def salidas_vigentes(salida: Path, sha256: str) -> bool:
    """Las salidas existen y corresponden al original con este sha256."""
    if not all((salida / s).exists() for s in SALIDAS):
        return False
    capturas = pd.read_parquet(salida / "capturas.parquet")
    return capturas.sha256.eq(sha256).any()


def procesar(entrada: Path, salida: Path, captura: dict, esperado: dict, fuentes: dict,
             resultado: str) -> Controles:
    with tempfile.TemporaryDirectory() as tmp:
        capas = leer_capas(abrir_entrada(entrada, Path(tmp)))

    territorios = construir_territorios(capas)
    obs = construir_observaciones(capas, territorios, captura["id"])
    corr = construir_correspondencias(capas)
    controles, comp = validar(capas, territorios, obs, esperado, fuentes[FUENTE_ID]["niveles_publicados"])

    territorios.to_parquet(salida / "territorios.parquet", index=False)
    obs.to_parquet(salida / "observaciones.parquet", index=False)
    corr.to_parquet(salida / "correspondencias.parquet", index=False)
    pd.DataFrame([{"codigo": c, "nombre": n, "unidad": u, "tema": TEMA[c], "columna_origen": col,
                   "fuente_id": FUENTE_ID, "nota": NOTA_INDICADORES}
                  for c, col, n, u in INDICADORES]).to_parquet(salida / "indicadores.parquet", index=False)
    pd.DataFrame([captura]).to_parquet(salida / "capturas.parquet", index=False)
    tabla_fuentes(fuentes).to_parquet(salida / "fuentes.parquet", index=False)
    escribir_duckdb(
        salida,
        ["territorios", "observaciones", "correspondencias", "indicadores", "capturas", "fuentes"],
        geometria={"territorios": "geom_wkb"},
        vistas={"v_observaciones": """
            SELECT o.*, t.nivel, t.codigo, t.nombre AS territorio, t.depto,
                   i.nombre AS indicador_nombre, i.unidad, c.fuente_id, c.fecha_proceso
            FROM observaciones o
            JOIN territorios t ON t.id = o.territorio_id
            JOIN indicadores i ON i.codigo = o.indicador
            JOIN capturas c ON c.id = o.captura_id
        """},
    )
    escribir_reporte(salida / "reporte_validacion.md", controles, comp, territorios, obs, captura, resultado)
    print(json.dumps({"resultado": resultado, "territorios": int(len(territorios)), "observaciones": int(len(obs)),
                      "controles_ok": len(controles.lista) - len(controles.fallas),
                      "controles_falla": len(controles.fallas)}, ensure_ascii=False))
    return controles


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path, help="zip del INE o carpeta con los .gpkg")
    ap.add_argument("--salida", type=Path, default=Path("datos/salida"))
    ap.add_argument("--esperado", type=Path, default=ESPERADO_COMPLETO,
                    help="yml con los valores esperados para los controles (por defecto, paquete completo)")
    ap.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes", help="carpeta del registro de fuentes")
    ap.add_argument("--forzar", action="store_true", help="reprocesar aunque el original no haya cambiado")
    args = ap.parse_args(argv)
    args.salida.mkdir(parents=True, exist_ok=True)

    fuentes = cargar_fuentes(args.fuentes)
    if FUENTE_ID not in fuentes:
        raise ValueError(f"Falta fuentes/{FUENTE_ID}.yml")
    esperado = cargar_esperado(args.esperado)

    sha, nombre = huella_entrada(args.entrada, [f"{c}.gpkg" for c in CAPAS])
    captura = nueva_captura(FUENTE_ID, nombre, sha, ahora())
    historial = Historial(args.salida)
    ultima = historial.ultima_procesada(FUENTE_ID)
    mismo_original = ultima is not None and ultima["sha256"] == sha

    # AC-P8: mismo original que la última captura procesada y salidas vigentes -> no se reprocesa.
    if mismo_original and not args.forzar and salidas_vigentes(args.salida, sha):
        historial.agregar(captura, "sin cambios", f"igual a la captura del {ultima['fecha_proceso']}")
        marcar_reporte(args.salida / "reporte_validacion.md", captura["fecha_proceso"], "sin cambios")
        print(json.dumps({"resultado": "sin cambios", "captura": captura["id"],
                          "ultima_procesada": ultima["fecha_proceso"]}, ensure_ascii=False))
        return 0

    resultado = "reprocesado" if mismo_original else "nuevo"
    try:
        controles = procesar(args.entrada, args.salida, captura, esperado, fuentes, resultado)
    except Exception as e:
        historial.agregar(captura, "error", f"{type(e).__name__}: {e}")
        raise
    codigo = controles.informar()
    if codigo:
        historial.agregar(captura, "error", "controles con falla: " + "; ".join(c["control"] for c in controles.fallas))
    else:
        historial.agregar(captura, resultado)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
