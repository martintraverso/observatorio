"""Archivos para la app estática (M2): todo lo que la app necesita, sin servidor.

Lee las salidas del pipeline (datos/salida/*.parquet) y escribe datos/salida/web/:

  territorios.pmtiles          todos los niveles, una capa por nivel (tippecanoe); segmento desde zoom 9
  <nivel>.geojson              geometrías simplificadas por cobertura, salvo segmento (AC-W2)
  territorios_index.json       índice de búsqueda: id, nivel, codigo, nombre, nombre_busqueda, depto, padre_id, bbox
  fichas/<nivel>/<codigo>.json todo lo que necesita la ficha de cada territorio (AC-W4)
  fichas/<nivel>/<codigo>/educacion.json  la educación de la ficha (MEC), aparte: la app la pide al ver la sección (#227)
  indicadores.json             catálogo de indicadores, con los niveles y períodos en que hay datos
  niveles.json                 catálogo de niveles: etiqueta, orden, si va al mapa, zoom mínimo y ámbito (M11)
  educacion_catalogo.json      cuadros del anuario del MEC con datos: código, título, tipo, años, si es por departamento, tasa del mapa (AC-E32)
  valores/<nivel>.json         valores de cada indicador por territorio, para pintar el mapa
  uruguay_mini.geojson         departamentos muy simplificados, para el mini-mapa de ubicación
  fuentes.json                 registro de fuentes
  capturas.json                capturas vigentes e historial de corridas
  manifest.json                cada archivo publicado con tamaño, sha256 y fecha de generación (AC-W5)
  descargas.json               archivos para descargar (página Datos): tamaño, sha256, fecha, licencia, cita

Además arma datos/salida/descargas/ (se publican como assets del release, AC-D1):
  observaciones.csv                    todas las observaciones con su origen
  territorios_<nivel>.parquet          GeoParquet por nivel, geometría completa
  territorios_<nivel>.geojson          GeoJSON por nivel, simplificado (5 decimales)

Uso:
  python pipeline/web.py [--salida datos/salida] [--sin-pmtiles]

Necesita tippecanoe (>= 2.17, escribe PMTiles) en el PATH; con --sin-pmtiles se saltea
ese archivo (solo para desarrollo local).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from comun.capturas import ARCHIVO_HISTORIAL, ahora
from comun.huella import sha256_archivo
from comun.registro import RAIZ, cargar_fuentes

ATRIBUCION = "Límites: INE, unidades geoestadísticas 2023"
DECIMALES = 5

# Niveles con GeoJSON y su tolerancia de simplificación (grados; ~0.001 = 100 m).
# Los niveles de un mismo grupo se simplifican juntos, como una sola cobertura.
GEOJSON = {
    "departamento": 0.002,
    "area_especial": 0.002,
    "seccion": 0.0015,
    "localidad": 0.0003,
    "barrio_mvd": 0.0002,
    "ccz_mvd": 0.0002,
    "pais": 0.002,
    "municipio_mvd": 0.0002,
}
GRUPOS_COBERTURA = [["departamento", "area_especial"], ["seccion"], ["localidad"], ["barrio_mvd"], ["ccz_mvd"],
                    ["pais"], ["municipio_mvd"]]

# Capas del PMTiles: nivel -> zoom mínimo en que aparece.
PMTILES_MINZOOM = {
    "departamento": 0, "area_especial": 0, "seccion": 0, "localidad": 0,
    "barrio_mvd": 0, "ccz_mvd": 0, "segmento": 9, "pais": 0, "municipio_mvd": 0,
}
PMTILES_MAXZOOM = 13  # la app hace overzoom; 14 duplicaba el tamaño (~26 MB)

# M11.1 (AC-N1): catálogo de niveles, de grueso a fino (orden de D2, #200). `en_mapa` es la decisión D1: qué niveles
# ofrece el selector del mapa (localidad no cubre el país; CCZ casi repite al municipio). La seccional policial
# (F5) se agrega acá, entre municipio y sección, con su capa en PMTILES_MINZOOM; la app no cambia (AC-N13).
# D2 ordena solo los niveles del mapa: los que no van (localidad, CCZ, área especial) quedan al final. Si D1 suma uno,
# hay que moverlo a su lugar de grueso a fino.
# `dentro_de`: los niveles que contienen enteros a cada territorio de este nivel. Al cambiar de indicador, el mapa va al
# más cercano de esos que se ofrezca (AC-N7, mantenedor en #202). Solo contenciones exactas: un barrio no se da por
# dentro de un municipio ni una seccional por dentro de otro nivel que el departamento.
NIVELES_CATALOGO = [
    {"id": "pais", "etiqueta": "País", "en_mapa": False, "ambito": "pais", "dentro_de": []},
    {"id": "region", "etiqueta": "Región", "en_mapa": False, "ambito": "pais", "dentro_de": ["pais"]},
    {"id": "departamento", "etiqueta": "Departamento", "en_mapa": True, "ambito": "pais", "dentro_de": ["pais"]},
    {"id": "municipio_mvd", "etiqueta": "Municipio", "ayuda": "Solo Montevideo", "en_mapa": True, "ambito": "montevideo",
     "dentro_de": ["pais", "departamento"]},
    {"id": "seccion", "etiqueta": "Sección", "en_mapa": True, "ambito": "pais", "dentro_de": ["pais", "departamento"]},
    {"id": "barrio_mvd", "etiqueta": "Barrio", "ayuda": "Solo Montevideo", "en_mapa": True, "ambito": "montevideo",
     "dentro_de": ["pais", "departamento"]},
    {"id": "segmento", "etiqueta": "Segmento", "en_mapa": True, "ambito": "pais",
     "dentro_de": ["pais", "departamento", "seccion"]},
    {"id": "localidad", "etiqueta": "Localidad", "en_mapa": False, "ambito": "pais", "dentro_de": ["pais", "departamento"]},
    {"id": "ccz_mvd", "etiqueta": "CCZ", "ayuda": "Solo Montevideo", "en_mapa": False, "ambito": "montevideo",
     "dentro_de": ["pais", "departamento"]},
    {"id": "area_especial", "etiqueta": "Área especial", "en_mapa": False, "ambito": "pais", "dentro_de": ["pais"]},
]

PROPIEDADES = ["id", "codigo", "nombre", "depto"]

# Mismo orden que TEMAS en app/src/lib/mapa/estado.ts.
ORDEN_TEMAS = ["Población", "Vivienda", "Hogares", "Trabajo", "Ingresos", "Educación"]

# Niveles que arma el pipeline uniendo geometrías del INE (F2.3).
DERIVADOS = {"pais", "municipio_mvd"}
# Niveles sin geometría (F3.2, AC-I3): no van a GeoJSON, PMTiles ni descargas por nivel; en el índice y las
# fichas llevan bbox = null. Igual que SIN_GEOMETRIA en territorios_2023.py.
SIN_GEOMETRIA = {"region"}


# ---------------------------------------------------------------- utilidades

def plegar(texto: str) -> str:
    """Minúsculas y sin tildes, para buscar: 'Paysandú' -> 'paysandu'."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c))
    return " ".join(sin_tildes.lower().split())


def numero(v):
    """1300197.0 -> 1300197; deja los no enteros como float."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    f = float(v)
    return int(f) if f.is_integer() else f


def fecha_iso(d) -> str:
    """Fecha de Parquet (date, Timestamp o texto) -> 'AAAA-MM-DD'."""
    return d.isoformat()[:10] if hasattr(d, "isoformat") else str(d)[:10]


def bbox(geom) -> list[float] | None:
    """Caja [oeste, sur, este, norte], redondeada hacia afuera a DECIMALES; None si no hay geometría."""
    if not isinstance(geom, shapely.Geometry):  # None o NaN (iterrows): niveles sin geometría (region)
        return None
    x0, y0, x1, y1 = geom.bounds
    k = 10 ** DECIMALES
    return [math.floor(x0 * k) / k, math.floor(y0 * k) / k, math.ceil(x1 * k) / k, math.ceil(y1 * k) / k]


def escribir_json(path: Path, datos) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def registros(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista de dicts con tipos JSON (listas de numpy, NaN -> None)."""
    filas = []
    for r in df.to_dict(orient="records"):
        fila = {}
        for k, v in r.items():
            if hasattr(v, "tolist"):
                v = v.tolist()
            elif isinstance(v, float) and math.isnan(v):
                v = None
            elif v is pd.NA:
                v = None
            fila[k] = v
        filas.append(fila)
    return filas


# ---------------------------------------------------------------- geometrías

def agujeros(geoms) -> list:
    """Agujeros de la unión de una cobertura (unión exacta para coberturas)."""
    union = shapely.coverage_union_all(geoms)
    return [shapely.Polygon(anillo) for p in shapely.get_parts(union) for anillo in p.interiors]


def rellenar_agujeros_nuevos(simple, original):
    """Cierra los agujeros que aparecen al simplificar y redondear y que no estaban en el original.

    Pasa cuando un entrante angosto del borde exterior se estrecha hasta cerrarse (ej. un arroyo
    entre secciones de Canelones: 44 m²). Cada agujero nuevo se suma al vecino con más borde
    compartido, así la cobertura sigue sin huecos ni solapes. Los agujeros del original se respetan.
    """
    simple = simple.copy()
    previos = shapely.union_all(agujeros(original)) if agujeros(original) else shapely.Polygon()
    for h in agujeros(simple):
        if shapely.intersection(h, previos).area >= 0.5 * h.area:
            continue
        borde = shapely.length(shapely.intersection(shapely.boundary(simple), h.boundary))
        i = int(borde.argmax())
        simple[i] = shapely.set_precision(shapely.union(simple[i], h), 10 ** -DECIMALES)
    return simple


def simplificar(territorios: gpd.GeoDataFrame, grupos=GRUPOS_COBERTURA, tolerancias=GEOJSON) -> gpd.GeoDataFrame:
    """Simplificación por cobertura (bordes compartidos se simplifican igual) y precisión de 5 decimales."""
    partes = []
    for grupo in grupos:
        g = territorios[territorios.nivel.isin(grupo)].copy()
        if g.empty:
            continue
        tol = max(tolerancias[n] for n in grupo)
        simple = shapely.set_precision(shapely.coverage_simplify(g.geometry.values, tol), 10 ** -DECIMALES)
        g["geometry"] = rellenar_agujeros_nuevos(simple, g.geometry.values)
        partes.append(g)
    return gpd.GeoDataFrame(pd.concat(partes), geometry="geometry", crs=territorios.crs)


def escribir_geojson(simplificados: gpd.GeoDataFrame, web: Path) -> list[str]:
    escritos = []
    for nivel in GEOJSON:
        g = simplificados[simplificados.nivel == nivel][[*PROPIEDADES, "padre_id", "geometry"]]
        if g.empty:
            continue
        destino = web / f"{nivel}.geojson"
        g.to_file(destino, driver="GeoJSON",
                  layer_options={"COORDINATE_PRECISION": DECIMALES, "RFC7946": "YES", "WRITE_NAME": "NO"})
        escritos.append(destino.name)
    return escritos


def tippecanoe() -> str | None:
    return shutil.which("tippecanoe")


def escribir_pmtiles(territorios: gpd.GeoDataFrame, web: Path) -> str:
    """Un PMTiles con una capa por nivel, desde las geometrías completas (tippecanoe simplifica por zoom)."""
    binario = tippecanoe()
    if binario is None:
        raise RuntimeError("No encuentro tippecanoe en el PATH (o usar --sin-pmtiles en desarrollo)")
    destino = web / "territorios.pmtiles"
    with tempfile.TemporaryDirectory() as tmp:
        capas = []
        for nivel, minzoom in PMTILES_MINZOOM.items():
            g = territorios[territorios.nivel == nivel]
            if g.empty:
                continue
            archivo = Path(tmp) / f"{nivel}.geojsonl"
            with open(archivo, "w", encoding="utf-8") as f:
                for r, geom in zip(g[PROPIEDADES].to_dict(orient="records"), g.geometry.values):
                    f.write(json.dumps({
                        "type": "Feature", "properties": r, "tippecanoe": {"minzoom": minzoom},
                        "geometry": shapely.geometry.mapping(geom),
                    }, ensure_ascii=False) + "\n")
            capas += ["-L", f"{nivel}:{archivo}"]
        subprocess.run([
            binario, "-o", str(destino), "--force", "--quiet",
            "-Z0", f"-z{PMTILES_MAXZOOM}",
            "--detect-shared-borders",          # vecinos simplificados igual, sin huecos
            "--no-feature-limit", "--no-tile-size-limit",  # no descartar territorios
            "-n", "Territorios INE 2023", "--attribution", ATRIBUCION,
            *capas,
        ], check=True)
    return destino.name


# ---------------------------------------------------------------- mapa

TOLERANCIA_MINI = 0.01  # grados (~1 km): solo para ubicar, no para medir


def valores_por_nivel(territorios: gpd.GeoDataFrame, obs: pd.DataFrame) -> dict[str, dict]:
    """{nivel: {"nivel", "indicadores": {ind: {periodo: {codigo: valor}}}, "estimados": {...}}}.

    Solo los valores guardados en ese nivel (nunca sumas de niveles menores).
    """
    t = territorios.set_index("id")[["nivel", "codigo"]]
    o = obs.join(t, on="territorio_id")
    salida = {}
    for nivel, g in o.groupby("nivel"):
        datos = {"nivel": nivel, "indicadores": {}, "estimados": {}}
        for (ind, periodo), h in g.sort_values("codigo").groupby(["indicador", "periodo"]):
            datos["indicadores"].setdefault(ind, {})[periodo] = {c: numero(v) for c, v in zip(h.codigo, h.valor)}
            est = h[h.es_estimado].codigo.tolist()
            if est:
                datos["estimados"].setdefault(ind, {})[periodo] = est
        salida[nivel] = datos
    return salida


def catalogo_niveles() -> list[dict]:
    """niveles.json (AC-N1): cada nivel con id, etiqueta, ayuda, orden, dibujable, zoom mínimo, ámbito y dentro_de.
    `dibujable`: el nivel va al mapa (D1) y tiene capa en el PMTiles; país y región nunca (AC-N3). `capa`: tiene capa en
    el PMTiles aunque no vaya al selector (localidad, CCZ): el mapa resalta ahí lo elegido en la búsqueda (M11.3)."""
    return [{
        "id": n["id"], "etiqueta": n["etiqueta"], "ayuda": n.get("ayuda"), "orden": i,
        "dibujable": n["en_mapa"] and n["id"] in PMTILES_MINZOOM and n["id"] not in SIN_GEOMETRIA,
        "capa": n["id"] in PMTILES_MINZOOM and n["id"] not in SIN_GEOMETRIA,
        "minzoom": PMTILES_MINZOOM.get(n["id"]) or None, "ambito": n["ambito"], "dentro_de": n["dentro_de"],
    } for i, n in enumerate(NIVELES_CATALOGO)]


def con_corte(indicadores: pd.DataFrame, registro: Path | None = None) -> pd.DataFrame:
    """F4.7b2 (#211, AC-E13/AC-E30): `corte` = el motivo de un indicador del anuario del MEC cuyo concepto cambia entre
    años («concepto distinto (AC-E13): …», del registro); vacío en los demás. La ficha corta ahí la serie y muestra la
    nota. Solo para la web: no cambia la base."""
    registro = registro or RAIZ / "fuentes" / "mec_anuario_educacion.yml"
    cortes: dict[str, str] = {}
    if registro.exists():
        import yaml

        for e in (yaml.safe_load(registro.read_text(encoding="utf-8")).get("cuadros") or {}).values():
            for m in (e.get("mapeo") or {}).values():
                for x in m or []:
                    if "AC-E13" in (x.get("motivo_d6") or ""):
                        cortes[x["id"]] = x["motivo_d6"].split(": ", 1)[-1]
    return indicadores.assign(corte=indicadores.codigo.map(cortes).fillna(""))


# #213: nivel educativo de un cuadro del anuario del MEC según su código (II-<nivel>.…), para agrupar en el mapa.
GRUPOS_EDUCACION = {"1": "Primera infancia e inicial", "2": "Primaria", "3": "Media básica", "4": "Media superior"}


def con_mapa(indicadores: pd.DataFrame) -> pd.DataFrame:
    """#213 (decisión del mantenedor en #193): `mapa` dice si el indicador va a la lista del mapa (de educación, solo
    las tasas calculadas; los demás temas, todos) y `grupo`, el nivel educativo del cuadro (vacío fuera de educación).
    Los demás valores de educación siguen en las fichas y en las descargas. Solo para la web: no cambia la base."""
    ind = indicadores if "cuadro" in indicadores else con_cuadro(indicadores)
    educacion = ind.tema == "Educación"
    nivel = ind.cuadro.fillna("").str.extract(r"^II-(\d+)\.")[0]
    return ind.assign(mapa=~educacion | ind.es_derivado.fillna(False).astype(bool),
                      grupo=nivel.map(GRUPOS_EDUCACION).where(educacion, "").fillna(""))


def catalogo_educacion(indicadores: pd.DataFrame, obs: pd.DataFrame, registro: Path | None = None) -> list[dict]:
    """F4.8a3 (#226, AC-E32): cada cuadro del anuario del MEC con datos en esta salida: código, título, tipo (A, B, C:
    el del último año con datos que lo tenga), años, si publica valores por departamento (`departamental`, de las
    observaciones: algunos B traen Montevideo) y una tasa calculada para abrirlo en el mapa (la que se dibuja por
    departamento, la más general primero). Sale del registro y de lo publicado; sin datos de educación, vacío."""
    from mec_anuario_cargar import legible

    ind = indicadores if "cuadro" in indicadores else con_cuadro(indicadores)
    ind = ind[ind.cuadro.fillna("") != ""]
    if ind.empty:
        return []
    registro = registro or RAIZ / "fuentes" / "mec_anuario_educacion.yml"
    import yaml

    cuadros = (yaml.safe_load(registro.read_text(encoding="utf-8")) or {}).get("cuadros", {}) if registro.exists() else {}
    o = obs[obs.indicador.isin(ind.codigo)].assign(cuadro=lambda d: d.indicador.map(dict(zip(ind.codigo, ind.cuadro))))
    anios = o.groupby("cuadro").periodo.agg(lambda x: sorted(set(x)))
    depto = o[o.territorio_id.str.contains("/departamento/", regex=False)]
    con_depto = set(depto.indicador)  # indicadores que se dibujan por departamento
    salida = []
    for cod in sorted(anios.index, key=lambda c: [int(x) for x in c[3:].split(".")]):
        e = cuadros.get(cod, {})
        tipos = {str(a): t for a, t in (e.get("tipos") or {}).items() if t}
        tipo = next((tipos[a] for a in reversed(anios[cod]) if a in tipos), "")  # II-2.2.15: 2024 sin tipo
        tasas = [c for c in ind[(ind.cuadro == cod) & ind.es_derivado.fillna(False).astype(bool)].codigo if c in con_depto]
        tasas.sort(key=lambda c: (c.count("__"), "total" not in c, len(c), c))  # la más general primero
        salida.append({"cuadro": cod, "titulo": legible(e.get("titulo", cod)), "tipo": tipo, "anios": anios[cod],
                       "departamental": bool(depto.cuadro.eq(cod).any()), "mapa": tasas[0] if tasas else None})
    return salida


def con_cuadro(indicadores: pd.DataFrame) -> pd.DataFrame:
    """F4.7a (#191, AC-E29/E31): el código del cuadro de origen de cada indicador del anuario del MEC («II-2.2.1»),
    tomado de su `columna_origen` («Cuadro II-2.2.1 · …»); vacío para los demás."""
    return indicadores.assign(cuadro=indicadores.columna_origen.fillna("").str.extract(r"^Cuadro (II-[\d.]+)")[0].fillna(""))


# M11.4 (AC-N6, mantenedor en #204): un nivel va al mapa de un indicador si tiene valor en al menos tantos territorios.
# Así lo que se publica para un solo territorio de un nivel (los ingresos de la ECH: Montevideo en «departamento») no
# arma un coroplético de un solo color; se muestra como comparación regional (AC-I20).
MIN_TERRITORIOS_MAPA = 2


def disponibilidad(indicadores: pd.DataFrame, territorios: gpd.GeoDataFrame, obs: pd.DataFrame) -> list[dict]:
    """indicadores.json: cada indicador con los niveles y períodos en que hay datos (AC-M2, AC-N2) y `niveles_mapa`:
    los niveles con valor en al menos MIN_TERRITORIOS_MAPA territorios (AC-N6). Los dos salen de las observaciones.
    AC-V33 (#247): `mapa` (de con_mapa) queda en true solo si hay un nivel dibujable en `niveles_mapa` o el indicador
    se publica por región (va a la comparación regional, AC-I20); si no, la lista del mapa no lo ofrece. Sigue en las
    fichas, el catálogo de educación y las descargas."""
    nivel = obs.territorio_id.map(territorios.set_index("id").nivel)
    dibujables = {n["id"] for n in catalogo_niveles() if n["dibujable"]}
    # En el orden de los temas de la app (el primero es el que muestra el mapa al abrir), no en el de las fuentes.
    orden = {t: i for i, t in enumerate(ORDEN_TEMAS)}
    indicadores = indicadores.assign(_o=indicadores.tema.map(orden).fillna(len(orden))).sort_values("_o", kind="stable")
    filas = registros(indicadores.drop(columns="_o"))
    for f in filas:
        de_este = obs.indicador == f["codigo"]
        f["niveles"] = sorted(nivel[de_este].unique().tolist())
        con_valor = de_este & obs.valor.notna()
        por_nivel = obs.territorio_id[con_valor].groupby(nivel[con_valor]).nunique()
        f["niveles_mapa"] = sorted(por_nivel[por_nivel >= MIN_TERRITORIOS_MAPA].index.tolist())
        f["periodos"] = sorted(obs.periodo[de_este].unique().tolist())
        if "mapa" in f:
            f["mapa"] = bool(f["mapa"]) and bool(set(f["niveles_mapa"]) & dibujables or "region" in f["niveles"])
    return filas


# M12.1b (#248, AC-V34/AC-V35): nombre corto, familia y apertura de los indicadores del mapa, de un registro revisado
# (no del título del MEC). Un indicador con `mapa: true` que no está en el registro frena el build.
REGISTRO_MAPA = RAIZ / "fuentes" / "mapa" / "indicadores.yml"
MAX_NOMBRE_CORTO = 48


class ErrorRegistroMapa(ValueError):
    pass


def leer_registro_mapa(registro: Path | None = None) -> tuple[dict[str, dict], dict[str, str]]:
    """{código: {nombre_corto, familia, apertura}} y {código: motivo} de los que no van al mapa. Valida AC-V34 (nombre
    corto: hasta 48 caracteres, sin código de cuadro, «/», «·» ni «*») y AC-V35 (combinaciones únicas en la familia)."""
    import yaml

    r = yaml.safe_load((registro or REGISTRO_MAPA).read_text(encoding="utf-8")) or {}
    entradas, errores = {}, []
    for total, f in (r.get("familias") or {}).items():
        entradas[total] = {"nombre_corto": f["nombre_corto"], "familia": total, "apertura": []}
        vistas = set()
        for codigo, a in (f.get("aperturas") or {}).items():
            par = [{"dimension": d, "valor": v} for d, v in (a.get("apertura") or {}).items()]
            clave = tuple((x["dimension"], x["valor"]) for x in par)
            if not par or clave in vistas:
                errores.append(f"{codigo}: apertura vacía o repetida en la familia {total} (AC-V35)")
            vistas.add(clave)
            entradas[codigo] = {"nombre_corto": a["nombre_corto"], "familia": total, "apertura": par}
    for codigo, e in entradas.items():
        n = e["nombre_corto"]
        if len(n) > MAX_NOMBRE_CORTO or re.search(r"[/·*]|\bII-\d", n):
            errores.append(f"{codigo}: nombre corto «{n}» (AC-V34: hasta {MAX_NOMBRE_CORTO} caracteres, sin «/», «·», «*» ni código de cuadro)")
    fuera = dict(r.get("fuera_del_mapa") or {})
    if dobles := sorted(set(fuera) & set(entradas)):
        errores.append(f"en familias y fuera del mapa a la vez: {dobles[:3]}")
    if errores:
        raise ErrorRegistroMapa("registro del mapa: " + "; ".join(errores[:5]))
    return entradas, fuera


def con_nombres_del_mapa(filas: list[dict], registro: Path | None = None) -> list[dict]:
    """AC-V34/AC-V35 (#248): a cada indicador con `mapa: true` le pone `nombre_corto`, `familia` y `apertura` del
    registro. Los de `fuera_del_mapa` pasan a `mapa: false` (siguen en fichas y descargas), y también una apertura cuyo
    total no está en el mapa: la familia siempre tiene su total. Uno que no está en el registro frena el build."""
    entradas, fuera = leer_registro_mapa(registro)
    en_mapa = [f for f in filas if f.get("mapa")]
    if faltan := sorted(f["codigo"] for f in en_mapa if f["codigo"] not in entradas and f["codigo"] not in fuera):
        raise ErrorRegistroMapa(f"{len(faltan)} indicadores del mapa sin nombre corto en {REGISTRO_MAPA.relative_to(RAIZ)} "
                                f"(AC-V34): {faltan[:5]}")
    for f in en_mapa:
        if f["codigo"] in fuera:
            f["mapa"] = False
    totales = {f["codigo"] for f in filas if f.get("mapa") and entradas[f["codigo"]]["familia"] == f["codigo"]}
    for f in filas:
        if f.get("mapa"):
            e = entradas[f["codigo"]]
            if e["familia"] not in totales:
                f["mapa"] = False
            else:
                f.update(e)
    return filas


def solo_activas(obs, indicadores, capturas, fuentes, historial, incluir_en_preparacion=False):
    """Lo que ve la app: solo valores, indicadores, capturas e historial de fuentes activas. Una fuente con
    `cargar: true` que todavía no es activa (p. ej. «en preparación» hasta pasar sus controles) queda en el
    release, no en la app. Con `incluir_en_preparacion` (vista previa local, F2.8a) entran también las fuentes
    «en preparación»: el workflow de datos nunca lo usa."""
    estados = {"activa", "en preparación"} if incluir_en_preparacion else {"activa"}
    visibles = set(fuentes.loc[fuentes.estado.isin(estados), "id"])
    capturas = capturas[capturas.fuente_id.isin(visibles)]
    return (obs[obs.captura_id.isin(capturas.id)], indicadores[indicadores.fuente_id.isin(visibles)], capturas,
            historial[historial.fuente_id.isin(visibles)])


def escribir_mini(territorios: gpd.GeoDataFrame, web: Path) -> None:
    """Departamentos (y área especial) muy simplificados, para el mini-mapa de ubicación."""
    g = territorios[territorios.nivel.isin(["departamento", "area_especial"])][["id", "codigo", "nivel", "geometry"]]
    g = g.copy()
    g["geometry"] = shapely.set_precision(shapely.coverage_simplify(g.geometry.values, TOLERANCIA_MINI), 1e-3)
    g.to_file(web / "uruguay_mini.geojson", driver="GeoJSON",
              layer_options={"COORDINATE_PRECISION": 3, "RFC7946": "YES", "WRITE_NAME": "NO"})


# ---------------------------------------------------------------- índice y fichas

def indice(territorios: gpd.GeoDataFrame) -> list[dict]:
    t = territorios.sort_values(["nivel", "codigo"])
    return [{
        "id": r.id, "nivel": r.nivel, "codigo": r.codigo, "nombre": r.nombre,
        "nombre_busqueda": plegar(r.nombre), "depto": r.depto,
        "padre_id": r.padre_id if isinstance(r.padre_id, str) else None, "bbox": bbox(r.geometry),
    } for r in t.itertuples()]


def advertencias_del_registro(carpeta: Path) -> dict[str, list[str]]:
    """Advertencias de cada fuente (campo `advertencias` del registro), para mostrarlas junto a sus datos
    (AC-L26). No van a la tabla `fuentes` del release: solo a la web, y solo las fuentes que las tienen."""
    return {k: list(f["advertencias"]) for k, f in cargar_fuentes(carpeta).items() if f.get("advertencias")}


def resumenes_del_registro(carpeta: Path) -> dict[str, str]:
    """Resumen de una o dos líneas de las advertencias (campo `resumen_advertencias`), lo que la app muestra
    siempre a la vista; la lista completa va plegada (AC-L26, AC-V23). Solo a la web, como las advertencias."""
    return {k: str(f["resumen_advertencias"]) for k, f in cargar_fuentes(carpeta).items() if f.get("resumen_advertencias")}


def construir_fichas(territorios, obs, indicadores, capturas, fuentes, correspondencias,
                     advertencias: dict[str, list[str]] | None = None,
                     resumenes: dict[str, str] | None = None) -> dict[str, dict]:
    t = territorios.set_index("id")
    padre = {i: p for i, p in t.padre_id.items() if isinstance(p, str)}

    def ancestros(i):
        cadena = []
        while i in padre:
            i = padre[i]
            cadena.append(i)
        return cadena[::-1]  # de la raíz hacia abajo

    obs_por_t = defaultdict(list)
    for r in obs.sort_values(["indicador", "periodo"]).itertuples():
        obs_por_t[r.territorio_id].append({
            "indicador": r.indicador, "periodo": r.periodo, "periodo_inicio": fecha_iso(r.periodo_inicio),
            "periodo_fin": fecha_iso(r.periodo_fin), "tipo_periodo": r.tipo_periodo, "valor": numero(r.valor),
            "es_estimado": bool(r.es_estimado), "captura_id": r.captura_id})

    def resumen(i):
        """Identidad y valores de un territorio, para listas de padres y contenidos."""
        valores, estimados = defaultdict(dict), []
        for o in obs_por_t.get(i, []):
            valores[o["indicador"]][o["periodo"]] = o["valor"]
            if o["es_estimado"]:
                estimados.append(f"{o['indicador']}/{o['periodo']}")
        r = {"id": i, "nivel": t.at[i, "nivel"], "codigo": t.at[i, "codigo"], "nombre": t.at[i, "nombre"],
             "valores": dict(valores)}
        if estimados:
            r["estimados"] = estimados
        return r

    # Contenidos: descendientes por padre_id, y segmentos de cada localidad por correspondencia.
    contenidos = defaultdict(lambda: defaultdict(list))
    for i in t.index:
        for a in ancestros(i):
            contenidos[a][t.at[i, "nivel"]].append(i)
    relaciones = defaultdict(list)
    for r in correspondencias.itertuples():
        if r.origen_id not in t.index:
            continue
        relaciones[r.origen_id].append({"tipo": r.tipo, "destino_id": r.destino_id, "metodo": r.metodo})
        if r.tipo == "pertenece_a" and r.destino_id in t.index:
            contenidos[r.destino_id][t.at[r.origen_id, "nivel"]].append(r.origen_id)

    def relacion(rel):
        """Relación con otro territorio. Si el código no tiene territorio propio (p. ej. CODLOC 'XX900',
        la parte rural del departamento, que el INE no publica como polígono de localidad), se informa
        igual, con existe = false: no se inventa el territorio."""
        _, nivel, codigo = rel["destino_id"].split("/")
        existe = rel["destino_id"] in t.index
        return {**rel, "nivel": nivel, "codigo": codigo,
                "nombre": t.at[rel["destino_id"], "nombre"] if existe else None, "existe": existe}

    ind = {r["codigo"]: r for r in registros(indicadores)}
    cap = {r["id"]: r for r in registros(capturas)}
    advertencias = advertencias or {}
    resumenes = resumenes or {}
    fue = {r["id"]: {**{k: r.get(k) for k in ("nombre", "organismo", "licencia", "pagina", "url_descarga")},
                     **({"advertencias": advertencias[r["id"]]} if r["id"] in advertencias else {}),
                     **({"resumen_advertencias": resumenes[r["id"]]} if r["id"] in resumenes else {})}
           for r in registros(fuentes)}

    # F3.7a (#148, AC-I22): fuera de Montevideo, la región del Interior y los temas con datos en ella (solo los temas:
    # los valores están en la ficha de la región). Sirve para «Ingresos: se publican para el Interior del país».
    interior = "INE-2023/region/interior"
    region = None
    if interior in t.index:
        temas = sorted({ind[o["indicador"]]["tema"] for o in obs_por_t.get(interior, []) if o["indicador"] in ind})
        region = {"id": interior, "nivel": "region", "codigo": t.at[interior, "codigo"], "nombre": t.at[interior, "nombre"],
                  "temas": temas}

    fichas = {}
    for i, fila in t.iterrows():
        observaciones = obs_por_t.get(i, [])
        padres = [resumen(a) for a in ancestros(i)]
        # Indicadores propios y los de los niveles que la contienen: la app los nombra y sabe su tema, p. ej.
        # para decir «Trabajo: se publica por departamento» en la ficha de un segmento (AC-V24). Solo metadatos:
        # los valores siguen en el nivel donde los publica la fuente.
        usadas = {o["indicador"] for o in observaciones} | {k for p in padres for k in p["valores"]}
        caps = {o["captura_id"] for o in observaciones}
        fichas[i] = {
            "id": i, "nivel": fila.nivel, "codigo": fila.codigo, "nombre": fila.nombre, "depto": fila.depto,
            "version_geo": fila.version_geo, "area_km2": None if pd.isna(fila.area_km2) else numero(round(fila.area_km2, 4)),
            "codigo_iso": fila.codigo_iso if isinstance(fila.codigo_iso, str) else None,
            "bbox": bbox(fila.geometry),
            "padres": padres,
            "contenidos": {n: [resumen(h) for h in sorted(set(hs))] for n, hs in sorted(contenidos[i].items())},
            "relaciones": [relacion(rel) for rel in relaciones.get(i, [])],
            "observaciones": observaciones,
            "indicadores": {k: ind[k] for k in sorted(usadas)},
            "capturas": {k: cap[k] for k in sorted(caps)},
            "fuentes": {f: fue[f] for f in sorted({cap[k]["fuente_id"] for k in caps})},
        }
        if region and fila.depto not in ("01", "") and fila.nivel not in ("pais", "region"):
            fichas[i]["region"] = region
    return fichas


def separar_educacion(f: dict, edu: set[str]) -> tuple[dict, dict | None]:
    """F4.10a (#227, decisión del mantenedor en #222): la educación de una ficha va en un archivo aparte
    (`fichas/<nivel>/<código>/educacion.json`) que la app pide al ver la sección. La ficha principal queda sin los
    valores de educación (los suyos y los de sus padres y contenidos) y lo avisa con `educacion: true` (en la ficha, si
    tiene valores propios; en cada padre o contenido que los tiene, para «Educación: datos por departamento», AC-V24).
    Las capturas y fuentes siguen todas en la principal (la cita nombra al MEC, AC-F6). La parte trae sus observaciones,
    sus indicadores y las capturas y fuentes de esas observaciones. Ficha principal + parte = la ficha completa."""
    def limpiar(r: dict) -> dict:
        valores = {k: v for k, v in r["valores"].items() if k not in edu}
        out = {**r, "valores": valores}
        if "estimados" in r:
            est = [e for e in r["estimados"] if e.split("/", 1)[0] not in edu]
            out.pop("estimados")
            if est:
                out["estimados"] = est
        if len(valores) < len(r["valores"]):
            out["educacion"] = True
        return out

    propias = [o for o in f["observaciones"] if o["indicador"] in edu]
    # Las capturas y fuentes quedan todas en la principal (pesan poco): la cita y «Fuentes de esta ficha» nombran al
    # MEC aunque la sección no se haya cargado (AC-F6, revisión de #235).
    principal = {**f, "padres": [limpiar(r) for r in f["padres"]],
                 "contenidos": {n: [limpiar(r) for r in rs] for n, rs in f["contenidos"].items()},
                 "observaciones": [o for o in f["observaciones"] if o["indicador"] not in edu],
                 "indicadores": {k: v for k, v in f["indicadores"].items() if k not in edu}}
    if not propias:
        return principal, None
    principal["educacion"] = True
    caps = {o["captura_id"] for o in propias}
    parte = {"observaciones": propias,
             "indicadores": {k: f["indicadores"][k] for k in sorted({o["indicador"] for o in propias})},
             "capturas": {k: f["capturas"][k] for k in sorted(caps)},
             "fuentes": {k: f["fuentes"][k] for k in sorted({f["capturas"][c]["fuente_id"] for c in caps})}}
    return principal, parte


# ---------------------------------------------------------------- descargas (página Datos, AC-D1/D2)

LICENCIA = "El uso es libre, citando como fuente al INE."
CITA = ("Observatorio Uruguay, a partir de INE, Unidades geoestadísticas Censo 2023. "
        "Indicar el archivo y la fecha de descarga.")
TOLERANCIA_SEGMENTO_DESCARGA = 0.0004
COLUMNAS_CSV = ["territorio_id", "nivel", "codigo", "nombre", "indicador", "periodo", "periodo_inicio", "periodo_fin",
                "tipo_periodo", "valor", "unidad", "es_estimado", "fuente", "archivo_origen", "sha256",
                "cuadro", "es_derivado"]  # F4.7a (#191, AC-E31): cuadro de origen (MEC) y si lo calculó el observatorio


def csv_observaciones(territorios, obs, indicadores, capturas, fuentes) -> pd.DataFrame:
    """Las mismas columnas que el CSV de cada ficha (AC-F5), para todas las observaciones."""
    t = territorios.set_index("id")[["nivel", "codigo", "nombre"]]
    ind = indicadores if "cuadro" in indicadores else con_cuadro(indicadores)
    if "es_derivado" not in ind:
        ind = ind.assign(es_derivado=False)
    o = obs.join(t, on="territorio_id").merge(
        ind[["codigo", "unidad", "cuadro", "es_derivado"]].rename(columns={"codigo": "indicador"}), on="indicador", how="left")
    c = capturas.rename(columns={"id": "captura_id", "archivo": "archivo_origen"})[
        ["captura_id", "fuente_id", "archivo_origen", "sha256"]]
    f = fuentes.assign(fuente=fuentes.organismo + " · " + fuentes.nombre)[["id", "fuente"]].rename(columns={"id": "fuente_id"})
    o = o.merge(c, on="captura_id", how="left").merge(f, on="fuente_id", how="left")
    o["es_estimado"] = o.es_estimado.map({True: "true", False: "false"})
    o["es_derivado"] = o.es_derivado.map(lambda v: "true" if v is True or v == True else "false")  # noqa: E712
    o["cuadro"] = o.cuadro.fillna("")
    o["periodo_inicio"] = o.periodo_inicio.map(fecha_iso)
    o["periodo_fin"] = o.periodo_fin.map(fecha_iso)
    return o[COLUMNAS_CSV].sort_values(["territorio_id", "indicador", "periodo"]).reset_index(drop=True)


def escribir_descargas(s: Path, territorios, obs, indicadores, capturas, fuentes, generado: str) -> dict:
    """Arma datos/salida/descargas/ y devuelve el contenido de web/descargas.json."""
    d = s / "descargas"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    archivos = []

    def registrar(path: Path, grupo: str, descripcion: str):
        archivos.append({"nombre": path.name, "grupo": grupo, "descripcion": descripcion,
                         "bytes": path.stat().st_size, "sha256": sha256_archivo(path)})

    registrar(s / "observaciones.parquet", "Observaciones", "Todos los valores con su indicador, territorio, período y captura.")
    csv_observaciones(territorios, obs, indicadores, capturas, fuentes).to_csv(d / "observaciones.csv", index=False)
    registrar(d / "observaciones.csv", "Observaciones",
              "Los valores que muestra la app (fuentes activas) en CSV, con nombre del territorio, unidad, fuente, "
              "archivo de origen, sha256, cuadro del anuario (educación) y si el valor lo calculó el observatorio.")

    simples = simplificar(territorios, [*GRUPOS_COBERTURA, ["segmento"]],
                          {**GEOJSON, "segmento": TOLERANCIA_SEGMENTO_DESCARGA})
    for nivel in ["pais", "departamento", "seccion", "segmento", "localidad", "barrio_mvd", "municipio_mvd", "ccz_mvd",
                  "area_especial"]:
        completo = territorios[territorios.nivel == nivel]
        if completo.empty:
            continue
        pq = d / f"territorios_{nivel}.parquet"
        completo.to_parquet(pq, index=False)
        origen = ("unión de geometrías del INE hecha por el pipeline" if nivel in DERIVADOS
                  else "geometría completa del INE")
        registrar(pq, "Territorios", f"{nivel}: {origen} (GeoParquet, EPSG:4326).")
        gj = d / f"territorios_{nivel}.geojson"
        simples[simples.nivel == nivel][[*PROPIEDADES, "padre_id", "geometry"]].to_file(
            gj, driver="GeoJSON", layer_options={"COORDINATE_PRECISION": DECIMALES, "RFC7946": "YES", "WRITE_NAME": "NO"})
        registrar(gj, "Territorios", f"{nivel}: geometría simplificada (GeoJSON, 5 decimales).")

    registrar(s / "territorios.parquet", "Territorios", "Todos los niveles juntos, con geometría completa (GeoParquet).")
    registrar(s / "correspondencias.parquet", "Territorios", "Relaciones entre territorios (segmento → localidad, CCZ → municipio, "
              "departamento → país, departamento → Interior).")
    registrar(s / "observatorio.duckdb", "Base completa", "Todo en una base DuckDB. Empezar por la vista v_observaciones.")
    registrar(s / "reporte_validacion.md", "Base completa", "Controles de calidad de la última corrida.")
    return {"generado": generado, "licencia": LICENCIA, "cita": CITA, "archivos": archivos}


def escribir_manifest(web: Path, generado: str, capturas) -> int:
    archivos = sorted(p for p in web.rglob("*") if p.is_file() and p.name != "manifest.json")
    escribir_json(web / "manifest.json", {
        "generado": generado,
        "capturas": sorted(capturas.id.tolist()),
        "archivos": [{"ruta": p.relative_to(web).as_posix(), "bytes": p.stat().st_size, "sha256": sha256_archivo(p)}
                     for p in archivos],
    })
    return len(archivos)


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=Path("datos/salida"))
    ap.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes", help="carpeta del registro de fuentes")
    ap.add_argument("--sin-pmtiles", action="store_true", help="no generar el PMTiles (desarrollo sin tippecanoe)")
    ap.add_argument("--incluir-en-preparacion", action="store_true",
                    help="vista previa local: incluir en la app las fuentes «en preparación» (no publicar; F2.8a)")
    args = ap.parse_args(argv)
    s = args.salida
    if not args.sin_pmtiles and tippecanoe() is None:
        print("No encuentro tippecanoe en el PATH. Instalarlo (ver README) o usar --sin-pmtiles.", file=sys.stderr)
        return 1

    territorios = gpd.read_parquet(s / "territorios.parquet")
    obs = pd.read_parquet(s / "observaciones.parquet")
    indicadores = pd.read_parquet(s / "indicadores.parquet")
    capturas = pd.read_parquet(s / "capturas.parquet")
    fuentes = pd.read_parquet(s / "fuentes.parquet")
    correspondencias = pd.read_parquet(s / "correspondencias.parquet")
    historial = pd.read_parquet(s / ARCHIVO_HISTORIAL) if (s / ARCHIVO_HISTORIAL).exists() else capturas.iloc[0:0]
    obs, indicadores, capturas, historial = solo_activas(  # F2.5d
        obs, indicadores, capturas, fuentes, historial, incluir_en_preparacion=args.incluir_en_preparacion)
    indicadores = con_mapa(con_corte(con_cuadro(indicadores)))
    if args.incluir_en_preparacion:
        print("Vista previa: incluye fuentes «en preparación». No publicar esta salida.", file=sys.stderr)

    web = s / "web"
    if web.exists():
        shutil.rmtree(web)  # se regenera entero: ningún archivo viejo queda publicado
    web.mkdir(parents=True)

    escribir_geojson(simplificar(territorios), web)
    if not args.sin_pmtiles:
        escribir_pmtiles(territorios, web)
    escribir_json(web / "territorios_index.json", indice(territorios))
    advertencias = advertencias_del_registro(args.fuentes)
    resumenes = resumenes_del_registro(args.fuentes)
    fichas = construir_fichas(territorios, obs, indicadores, capturas, fuentes, correspondencias, advertencias, resumenes)
    edu = set(indicadores.codigo[indicadores.tema == "Educación"])
    for f in fichas.values():
        principal, parte = separar_educacion(f, edu)  # F4.10a (#227): la educación, aparte
        escribir_json(web / "fichas" / f["nivel"] / f"{f['codigo']}.json", principal)
        if parte:
            escribir_json(web / "fichas" / f["nivel"] / f["codigo"] / "educacion.json", parte)
    escribir_json(web / "indicadores.json", con_nombres_del_mapa(disponibilidad(indicadores, territorios, obs)))
    escribir_json(web / "niveles.json", catalogo_niveles())
    escribir_json(web / "educacion_catalogo.json", catalogo_educacion(indicadores, obs))
    for nivel, datos in valores_por_nivel(territorios, obs).items():
        escribir_json(web / "valores" / f"{nivel}.json", datos)
    escribir_mini(territorios, web)
    escribir_json(web / "fuentes.json", [{**r, **({"advertencias": advertencias[r["id"]]} if r["id"] in advertencias else {}),
                                          **({"resumen_advertencias": resumenes[r["id"]]} if r["id"] in resumenes else {})}
                                         for r in registros(fuentes)])
    escribir_json(web / "capturas.json", {"vigentes": registros(capturas), "historial": registros(historial)})
    generado = ahora()
    escribir_json(web / "descargas.json",
                  escribir_descargas(s, territorios, obs, indicadores, capturas, fuentes, generado))
    n = escribir_manifest(web, generado, capturas)

    tamanos = {p.name: p.stat().st_size for p in sorted(web.glob("*.*"))}
    print(json.dumps({"archivos": n, "fichas": len(fichas), "pmtiles": not args.sin_pmtiles,
                      "tamanos_mb": {k: round(v / 1e6, 2) for k, v in tamanos.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
