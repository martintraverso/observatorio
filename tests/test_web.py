"""Pruebas de los archivos para la app (AC-W1…W5). Corren en los dos modos (fixture / completo)."""

from __future__ import annotations

import gzip
import json
import re

import geopandas as gpd
import pytest
import shapely
from pmtiles.reader import MmapSource, Reader, all_tiles
from web import GEOJSON, GRUPOS_COBERTURA, PMTILES_MINZOOM, agujeros, plegar

from comun.huella import sha256_archivo

DECIMALES_MAX = 5
MAX_GEOJSON = 2_000_000
MAX_INDICE_GZ = 1_000_000


@pytest.fixture(scope="session")
def territorios(salida):
    return gpd.read_parquet(salida / "territorios.parquet")


@pytest.fixture(scope="session")
def conteo(territorios):
    return territorios.nivel.value_counts().to_dict()


# ------------------------------------------------------------------ AC-W1

def test_cada_nivel_tiene_geometria_para_el_navegador(web, conteo):
    for nivel in conteo:
        if nivel == "segmento":
            assert not (web / "segmento.geojson").exists()  # demasiado pesado: solo PMTiles
        else:
            assert (web / f"{nivel}.geojson").exists(), nivel


def test_pmtiles_tiene_una_capa_por_nivel_con_todos_los_territorios(pmtiles, conteo):
    with open(pmtiles, "rb") as f:
        r = Reader(MmapSource(f))
        header, meta = r.header(), r.metadata()
    assert header["tile_type"].name == "MVT"
    assert {c["id"] for c in meta["vector_layers"]} == set(conteo)
    stats = meta["tilestats"] if "tilestats" in meta else json.loads(meta["json"])["tilestats"]
    assert {c["layer"]: c["count"] for c in stats["layers"]} == conteo
    assert "INE" in meta["attribution"]
    campos = {c["id"]: set(c["fields"]) for c in meta["vector_layers"]}
    assert all(campos[n] == {"id", "codigo", "nombre", "depto"} for n in conteo)

    # Los segmentos solo se cargan con zoom (AC-G6): ninguna tesela de zoom bajo los trae.
    # (El nombre de capa y los id "INE-2023/segmento/..." aparecen como texto en la tesela.)
    con_segmentos = set()
    with open(pmtiles, "rb") as f:
        for (z, _, _), datos in all_tiles(Reader(MmapSource(f)).get_bytes):
            if b"segmento" in gzip.decompress(datos):
                con_segmentos.add(z)
    assert con_segmentos and min(con_segmentos) == PMTILES_MINZOOM["segmento"]


# ------------------------------------------------------------------ AC-W2

@pytest.fixture(scope="session")
def geojson(web):
    return {n: web / f"{n}.geojson" for n in GEOJSON if (web / f"{n}.geojson").exists()}


def test_geojson_pesa_hasta_2_mb(geojson):
    grandes = {n: p.stat().st_size for n, p in geojson.items() if p.stat().st_size > MAX_GEOJSON}
    assert grandes == {}


def test_geojson_coordenadas_con_hasta_5_decimales(geojson):
    decimales = re.compile(r"-?\d+\.(\d+)")
    for nivel, p in geojson.items():
        datos = json.loads(p.read_text(encoding="utf-8"), parse_float=str)

        def coords(x):
            if isinstance(x, list):
                for y in x:
                    yield from coords(y)
            else:
                yield x

        largos = {len(m.group(1)) for f in datos["features"] for c in coords(f["geometry"]["coordinates"])
                  if (m := decimales.fullmatch(c))}
        assert max(largos, default=0) <= DECIMALES_MAX, nivel


def test_geojson_tiene_todos_los_territorios_y_geometrias_validas(geojson, territorios):
    for nivel, p in geojson.items():
        g = gpd.read_file(p)
        assert sorted(g["id"]) == sorted(territorios[territorios.nivel == nivel].id), nivel
        assert g.geometry.is_valid.all() and (~g.geometry.is_empty).all(), nivel
        assert set(g.columns) == {"id", "codigo", "nombre", "depto", "padre_id", "geometry"}


def test_simplificacion_mantiene_bordes_compartidos(geojson, territorios):
    """Los vecinos siguen encajando: sin solapes, bordes que coinciden, sin agujeros nuevos, misma área.

    El original del INE ya tiene algunos huecos angostos (< 10 m) y entrantes hacia el exterior;
    se exige no empeorarlo, no que desaparezcan.
    """
    for grupo in GRUPOS_COBERTURA:
        presentes = [n for n in grupo if n in geojson]
        if not presentes:
            continue
        simple = gpd.GeoDataFrame(
            gpd.pd.concat([gpd.read_file(geojson[n]) for n in presentes]), crs=4326).sort_values("id")
        original = territorios[territorios.nivel.isin(presentes)].sort_values("id")

        assert shapely.coverage_is_valid(simple.geometry.values), grupo  # sin solapes, bordes iguales

        assert len(agujeros(simple.geometry.values)) <= len(agujeros(original.geometry.values)), grupo
        a0 = shapely.coverage_union_all(original.geometry.values).area
        a1 = shapely.coverage_union_all(simple.geometry.values).area
        assert abs(a1 - a0) / a0 < 0.001, grupo


# ------------------------------------------------------------------ AC-W3

@pytest.fixture(scope="session")
def indice(web):
    return json.loads((web / "territorios_index.json").read_text(encoding="utf-8"))


def test_indice_lista_cada_territorio(indice, territorios):
    assert sorted(t["id"] for t in indice) == sorted(territorios.id)
    campos = {"id", "nivel", "codigo", "nombre", "nombre_busqueda", "depto", "padre_id", "bbox"}
    assert all(set(t) == campos for t in indice)
    por_id = territorios.set_index("id")
    for t in indice:
        x0, y0, x1, y1 = t["bbox"]
        b = por_id.loc[t["id"]].geometry.bounds
        assert x0 <= b[0] and y0 <= b[1] and x1 >= b[2] and y1 >= b[3], t["id"]  # la caja contiene al territorio


def test_indice_pesa_hasta_1_mb_comprimido(web):
    assert len(gzip.compress((web / "territorios_index.json").read_bytes())) <= MAX_INDICE_GZ


def test_nombre_busqueda_sin_tildes_ni_mayusculas(indice):
    por_codigo = {(t["nivel"], t["codigo"]): t for t in indice}
    assert por_codigo[("departamento", "16")]["nombre_busqueda"] == "san jose"
    assert plegar("Paysandú") == "paysandu" and plegar("  RÍO   Negro ") == "rio negro"
    assert all(t["nombre_busqueda"] == plegar(t["nombre"]) for t in indice)


# ------------------------------------------------------------------ AC-W4

def test_cada_territorio_tiene_ficha(web, territorios):
    faltan = [r.id for r in territorios.itertuples()
              if not (web / "fichas" / r.nivel / f"{r.codigo}.json").exists()]
    assert faltan == []
    assert sum(1 for _ in (web / "fichas").rglob("*.json")) == len(territorios)


def ficha(web, nivel, codigo):
    return json.loads((web / "fichas" / nivel / f"{codigo}.json").read_text(encoding="utf-8"))


def test_ficha_de_segmento_tiene_padres_localidad_y_fuentes(web, con):
    codigo = con.execute("select codigo from territorios where nivel = 'segmento' order by codigo limit 1").fetchone()[0]
    f = ficha(web, "segmento", codigo)
    assert [p["nivel"] for p in f["padres"]] == ["departamento", "seccion"]
    assert f["padres"][-1]["id"] == f"INE-2023/seccion/{codigo[:4]}"
    assert "pob_total" in f["padres"][0]["valores"]  # "Más datos en los niveles que contienen este territorio"
    loc = con.execute("select destino_id from correspondencias where origen_id = ?", [f["id"]]).fetchone()[0]
    assert [r["destino_id"] for r in f["relaciones"]] == [loc]
    existe = con.execute("select count(*) from territorios where id = ?", [loc]).fetchone()[0] == 1
    assert f["relaciones"][0]["existe"] is existe
    assert (f["relaciones"][0]["nombre"] is not None) is existe
    # Observaciones = las de la base, cada una con su captura, indicador y fuente en la ficha.
    db = con.execute("select indicador, periodo, valor, es_estimado, captura_id from observaciones "
                     "where territorio_id = ? order by indicador, periodo", [f["id"]]).fetchall()
    assert [(o["indicador"], o["periodo"], o["valor"], o["es_estimado"], o["captura_id"])
            for o in f["observaciones"]] == db
    assert all((o["tipo_periodo"], o["periodo_inicio"], o["periodo_fin"]) == ("censo", "2023-01-01", "2023-01-01")
               for o in f["observaciones"])
    for o in f["observaciones"]:
        c = f["capturas"][o["captura_id"]]
        assert c["sha256"] and c["archivo"]
        assert c["fuente_id"] in f["fuentes"] and o["indicador"] in f["indicadores"]


def test_ficha_de_departamento_tiene_contenidos(web, con):
    f = ficha(web, "departamento", "07")
    assert f["nombre"] == "Flores" and f["padres"] == []
    for nivel in ("seccion", "segmento", "localidad"):
        db = {r[0] for r in con.execute(
            "select id from territorios where nivel = ? and depto = '07'", [nivel]).fetchall()}
        assert {h["id"] for h in f["contenidos"][nivel]} == db, nivel
    assert all("pob_total" in h["valores"] for h in f["contenidos"]["seccion"])


def test_ficha_de_localidad_lista_sus_segmentos(web, con):
    loc, n = con.execute("""
        select destino_id, count(*) from correspondencias group by destino_id order by 2 desc limit 1
    """).fetchone()
    f = ficha(web, "localidad", loc.split("/")[-1])
    assert len(f["contenidos"]["segmento"]) == n


def test_ficha_del_limite_contestado_no_tiene_observaciones(web):
    f = ficha(web, "area_especial", "02-limite-contestado")
    assert f["observaciones"] == [] and f["padres"][0]["id"] == "INE-2023/departamento/02"


# ------------------------------------------------------------------ AC-W5

def test_manifest_lista_cada_archivo_con_tamano_y_sha256(web):
    m = json.loads((web / "manifest.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", m["generado"])
    en_disco = {p.relative_to(web).as_posix() for p in web.rglob("*") if p.is_file()} - {"manifest.json"}
    assert {a["ruta"] for a in m["archivos"]} == en_disco
    for a in m["archivos"][:: max(1, len(m["archivos"]) // 200)] + m["archivos"][-5:]:  # muestra + los últimos
        p = web / a["ruta"]
        assert a["bytes"] == p.stat().st_size and a["sha256"] == sha256_archivo(p), a["ruta"]
    assert m["capturas"]


# ------------------------------------------------------------------ datos para el mapa (M6)

def test_valores_por_nivel_son_los_guardados(web, con):
    """valores/<nivel>.json tiene exactamente las observaciones de ese nivel (nunca sumas)."""
    niveles = [r[0] for r in con.execute("""
        select distinct t.nivel from observaciones o join territorios t on t.id = o.territorio_id
    """).fetchall()]
    assert sorted(p.stem for p in (web / "valores").glob("*.json")) == sorted(niveles)
    for nivel in niveles:
        v = json.loads((web / "valores" / f"{nivel}.json").read_text(encoding="utf-8"))
        assert v["nivel"] == nivel
        db = con.execute("""
            select o.indicador, o.periodo, t.codigo, o.valor from observaciones o
            join territorios t on t.id = o.territorio_id where t.nivel = ?
        """, [nivel]).fetchall()
        en_archivo = [(i, p, c, val) for i, ps in v["indicadores"].items() for p, cs in ps.items()
                      for c, val in cs.items()]
        assert sorted(en_archivo) == sorted(db), nivel


def test_indicadores_dicen_donde_hay_datos(web, con):
    ind = json.loads((web / "indicadores.json").read_text(encoding="utf-8"))
    for i in ind:
        niveles = {r[0] for r in con.execute("""
            select distinct t.nivel from observaciones o join territorios t on t.id = o.territorio_id
            where o.indicador = ?
        """, [i["codigo"]]).fetchall()}
        assert set(i["niveles"]) == niveles and i["periodos"] == ["2023"] and i["tema"]
    assert "area_especial" not in {n for i in ind for n in i["niveles"]}


def test_mini_mapa_liviano_con_departamentos(web, conteo):
    g = gpd.read_file(web / "uruguay_mini.geojson")
    assert len(g) == conteo["departamento"] + conteo.get("area_especial", 0)
    assert g.geometry.is_valid.all()
    assert (web / "uruguay_mini.geojson").stat().st_size < 150_000


# ------------------------------------------------------------------ descargas (AC-D1, AC-D2)

def test_descargas_completas_con_tamano_y_sha256(salida, web, territorios, con):
    d = json.loads((web / "descargas.json").read_text(encoding="utf-8"))
    assert d["licencia"] and d["cita"] and re.fullmatch(r"\d{4}-\d\d-\d\dT.*", d["generado"])
    nombres = {a["nombre"] for a in d["archivos"]}
    assert {"observaciones.parquet", "observaciones.csv", "territorios.parquet", "observatorio.duckdb"} <= nombres
    for nivel in territorios.nivel.unique():
        assert {f"territorios_{nivel}.parquet", f"territorios_{nivel}.geojson"} <= nombres, nivel
    for a in d["archivos"]:
        p = salida / "descargas" / a["nombre"]
        p = p if p.exists() else salida / a["nombre"]
        assert a["bytes"] == p.stat().st_size and a["sha256"] == sha256_archivo(p), a["nombre"]
        assert a["descripcion"] and a["grupo"]


def test_csv_de_observaciones(salida, con):
    csv = gpd.pd.read_csv(salida / "descargas" / "observaciones.csv",
                          dtype={"codigo": str, "periodo": str, "periodo_inicio": str, "periodo_fin": str})
    assert list(csv.columns) == ["territorio_id", "nivel", "codigo", "nombre", "indicador", "periodo", "periodo_inicio",
                                 "periodo_fin", "tipo_periodo", "valor", "unidad", "es_estimado", "fuente",
                                 "archivo_origen", "sha256"]
    assert len(csv) == con.execute("select count(*) from observaciones").fetchone()[0]
    # valor puede venir vacío si el INE no lo publica (barrio 'N/a', código 1000000); el resto no.
    assert csv.drop(columns='valor').notna().all().all()
    flores = csv[(csv.territorio_id == "INE-2023/departamento/07") & (csv.indicador == "pob_total")]
    assert flores.valor.tolist() == [26271] and flores.unidad.tolist() == ["personas"]
    assert flores[["periodo_inicio", "periodo_fin", "tipo_periodo"]].values.tolist() == [["2023-01-01", "2023-01-01", "censo"]]


def test_territorios_por_nivel_completos(salida, territorios):
    for nivel, n in territorios.nivel.value_counts().items():
        completo = gpd.read_parquet(salida / "descargas" / f"territorios_{nivel}.parquet")
        assert len(completo) == n and completo.geometry.is_valid.all(), nivel
        simple = gpd.read_file(salida / "descargas" / f"territorios_{nivel}.geojson")
        assert sorted(simple["id"]) == sorted(completo["id"]), nivel


# F2.5d (#59): una fuente que se carga pero no está activa no aparece en la app
def test_la_app_muestra_solo_fuentes_activas():
    import pandas as pd
    from web import solo_activas

    fuentes = pd.DataFrame([{"id": "a", "estado": "activa"}, {"id": "b", "estado": "en preparación"}])
    capturas = pd.DataFrame([{"id": "a:1", "fuente_id": "a"}, {"id": "b:1", "fuente_id": "b"}])
    indicadores = pd.DataFrame([{"codigo": "x", "fuente_id": "a"}, {"codigo": "y", "fuente_id": "b"}])
    obs = pd.DataFrame([{"indicador": "x", "captura_id": "a:1"}, {"indicador": "y", "captura_id": "b:1"}])
    o, i, c = solo_activas(obs, indicadores, capturas, fuentes)
    assert o.indicador.tolist() == ["x"] and i.codigo.tolist() == ["x"] and c.id.tolist() == ["a:1"]
