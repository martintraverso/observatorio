"""Pruebas de los archivos para la app (AC-W1…W5). Corren en los dos modos (fixture / completo)."""

from __future__ import annotations

import gzip
import json
import re
import subprocess
import sys

import geopandas as gpd
import pytest
import shapely
from pmtiles.reader import MmapSource, Reader, all_tiles
from web import GEOJSON, GRUPOS_COBERTURA, PMTILES_MINZOOM, SIN_GEOMETRIA, agujeros, plegar

from comun.huella import sha256_archivo

DECIMALES_MAX = 5
MAX_GEOJSON = 2_000_000
MAX_INDICE_GZ = 1_000_000


@pytest.fixture(scope="session")
def territorios(salida):
    return gpd.read_parquet(salida / "territorios.parquet")


@pytest.fixture(scope="session")
def conteo(territorios):
    """Territorios por nivel, de los niveles con geometría (region no tiene: F3.2, AC-I3)."""
    return territorios[~territorios.nivel.isin(SIN_GEOMETRIA)].nivel.value_counts().to_dict()


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
        if t["nivel"] in SIN_GEOMETRIA:
            assert t["bbox"] is None, t["id"]
            continue
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
    # una ficha por territorio; los `educacion.json` de cada ficha van aparte (#227)
    assert sum(1 for p in (web / "fichas").rglob("*.json") if p.name != "educacion.json") == len(territorios)


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


def test_ficha_describe_los_indicadores_de_sus_padres(web):
    """AC-V24: la ficha trae nombre y tema de cada indicador que tienen los niveles que la contienen, para
    enlazarlos cuando un tema no se publica a su nivel. Las observaciones siguen siendo solo las propias."""
    revisadas = 0
    for archivo in sorted((web / "fichas" / "segmento").glob("*.json"))[:200]:
        f = json.loads(archivo.read_text(encoding="utf-8"))
        for p in f["padres"]:
            for k in p["valores"]:
                assert k in f["indicadores"] and f["indicadores"][k]["tema"], (f["id"], k)
                revisadas += 1
        propias = {o["indicador"] for o in f["observaciones"]}
        assert all(o["captura_id"] in f["capturas"] for o in f["observaciones"]) and propias <= set(f["indicadores"])
    assert revisadas


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
    """valores/<nivel>.json tiene exactamente las observaciones de ese nivel (nunca sumas), de las fuentes
    activas: una fuente con `cargar: true` todavía no activa no está en la app (F2.5d)."""
    niveles = [r[0] for r in con.execute("""
        select distinct t.nivel from observaciones o join territorios t on t.id = o.territorio_id
        join capturas c on c.id = o.captura_id join fuentes f on f.id = c.fuente_id and f.estado = 'activa'
    """).fetchall()]
    assert sorted(p.stem for p in (web / "valores").glob("*.json")) == sorted(niveles)
    for nivel in niveles:
        v = json.loads((web / "valores" / f"{nivel}.json").read_text(encoding="utf-8"))
        assert v["nivel"] == nivel
        db = con.execute("""
            select o.indicador, o.periodo, t.codigo, o.valor from observaciones o
            join territorios t on t.id = o.territorio_id
            join capturas c on c.id = o.captura_id join fuentes f on f.id = c.fuente_id and f.estado = 'activa' where t.nivel = ?
        """, [nivel]).fetchall()
        en_archivo = [(i, p, c, val) for i, ps in v["indicadores"].items() for p, cs in ps.items()
                      for c, val in cs.items()]
        assert sorted(en_archivo) == sorted(db), nivel


def test_indicadores_dicen_donde_hay_datos(web, con):
    ind = json.loads((web / "indicadores.json").read_text(encoding="utf-8"))
    assert all("cuadro" in i and "es_derivado" in i for i in ind)  # F4.7a: main() pasa por con_cuadro
    for i in ind:
        niveles = {r[0] for r in con.execute("""
            select distinct t.nivel from observaciones o join territorios t on t.id = o.territorio_id
            where o.indicador = ?
        """, [i["codigo"]]).fetchall()}
        periodos = sorted(r[0] for r in con.execute(
            "select distinct periodo from observaciones where indicador = ?", [i["codigo"]]).fetchall())
        assert set(i["niveles"]) == niveles and i["periodos"] == periodos and i["tema"]
        assert set(i["niveles_mapa"]) <= niveles  # AC-N6: subconjunto de los niveles con datos
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
    for nivel in set(territorios.nivel) - SIN_GEOMETRIA:
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
                                 "archivo_origen", "sha256", "cuadro", "es_derivado"]
    assert len(csv) == con.execute("""select count(*) from observaciones o
        join capturas c on c.id = o.captura_id join fuentes f on f.id = c.fuente_id and f.estado = 'activa'""").fetchone()[0]  # lo que muestra la app (fuentes activas)
    # valor puede venir vacío si el INE no lo publica (barrio 'N/a', código 1000000); el resto no.
    assert csv.drop(columns=['valor', 'cuadro']).notna().all().all()  # cuadro: solo en los valores del MEC
    flores = csv[(csv.territorio_id == "INE-2023/departamento/07") & (csv.indicador == "pob_total")]
    assert flores.valor.tolist() == [26271] and flores.unidad.tolist() == ["personas"]
    assert flores[["periodo_inicio", "periodo_fin", "tipo_periodo"]].values.tolist() == [["2023-01-01", "2023-01-01", "censo"]]


def test_territorios_por_nivel_completos(salida, conteo):
    for nivel, n in conteo.items():
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
    historial = capturas.assign(resultado="nuevo")
    o, i, c, h = solo_activas(obs, indicadores, capturas, fuentes, historial)
    assert o.indicador.tolist() == ["x"] and i.codigo.tolist() == ["x"] and c.id.tolist() == ["a:1"]
    assert h.fuente_id.tolist() == ["a"]
    # F2.8a (#65): la vista previa local suma las fuentes «en preparación»
    o, i, c, h = solo_activas(obs, indicadores, capturas, fuentes, historial, incluir_en_preparacion=True)
    assert o.indicador.tolist() == ["x", "y"] and c.id.tolist() == ["a:1", "b:1"] and h.fuente_id.tolist() == ["a", "b"]
    a_relevar = fuentes.assign(estado=["activa", "a relevar"])
    o, *_ = solo_activas(obs, indicadores, capturas, a_relevar, historial, incluir_en_preparacion=True)
    assert o.indicador.tolist() == ["x"]


def test_vista_previa_es_una_opcion_de_web_py_que_no_usa_el_workflow():
    """El workflow de datos arma la web sin la opción: lo publicado no cambia (F2.8a, #65)."""
    from conftest import RAIZ

    workflows = "".join(p.read_text(encoding="utf-8") for p in (RAIZ / ".github" / "workflows").glob("*.yml"))
    assert "--incluir-en-preparacion" not in workflows
    assert "--incluir-en-preparacion" not in (RAIZ / "pipeline" / "correr.py").read_text(encoding="utf-8")
    r = subprocess.run([sys.executable, str(RAIZ / "pipeline" / "web.py"), "--help"], capture_output=True, text=True)
    assert "--incluir-en-preparacion" in r.stdout


def test_la_salida_de_la_app_no_tiene_nada_de_fuentes_no_activas(web):
    """Sobre lo que genera web.py: nada de fuentes que no estén activas (hoy todas las cargadas lo están)."""
    fuentes = json.loads((web / "fuentes.json").read_text(encoding="utf-8"))
    activas = {f["id"] for f in fuentes if f["estado"] == "activa"}
    capturas = json.loads((web / "capturas.json").read_text(encoding="utf-8"))
    assert {c["fuente_id"] for c in capturas["vigentes"] + capturas["historial"]} <= activas
    ids = {c["id"] for c in capturas["vigentes"]}
    ind = json.loads((web / "indicadores.json").read_text(encoding="utf-8"))
    assert {i["fuente_id"] for i in (ind if isinstance(ind, list) else ind.values())} <= activas
    for f in list((web / "fichas").glob("*/*.json"))[:200]:
        ficha = json.loads(f.read_text(encoding="utf-8"))
        assert {o["captura_id"] for o in ficha["observaciones"]} <= ids, f


# F2.8d (#68): advertencias del INE de cada fuente, del registro, para mostrarlas junto a sus datos (AC-L26)
def test_las_advertencias_del_registro_llegan_a_la_web_solo_si_la_fuente_las_tiene(web):
    from comun.registro import RAIZ, cargar_fuentes

    registro = cargar_fuentes(RAIZ / "fuentes")
    fuentes = {f["id"]: f for f in json.loads((web / "fuentes.json").read_text(encoding="utf-8"))}
    for fid, f in registro.items():
        if f.get("advertencias"):
            assert fuentes[fid]["advertencias"] == f["advertencias"]
        else:
            assert "advertencias" not in fuentes[fid]  # sin cambios para las demás fuentes (el Censo)
    for archivo in list((web / "fichas").glob("*/*.json"))[:50]:
        for fid, ref in json.loads(archivo.read_text(encoding="utf-8"))["fuentes"].items():
            assert ref.get("advertencias") == (registro[fid].get("advertencias") or None)


def test_construir_fichas_suma_las_advertencias_de_la_fuente(salida):
    """Lo que la app muestra junto a los datos de trabajo (AC-L26), probado en CI con una fuente de ejemplo."""
    import geopandas as gpd
    import pandas as pd
    from web import construir_fichas

    t = gpd.read_parquet(salida / "territorios.parquet")
    obs = pd.read_parquet(salida / "observaciones.parquet")
    capturas = pd.read_parquet(salida / "capturas.parquet")
    fuentes = pd.read_parquet(salida / "fuentes.parquet")
    # el Censo: está en todas las salidas (con datos completos también hay ECH, y no en todas las fichas)
    fid = "ine_unidades_geoestadisticas_2023"
    fichas = construir_fichas(t, obs, pd.read_parquet(salida / "indicadores.parquet"), capturas, fuentes,
                              pd.read_parquet(salida / "correspondencias.parquet"), {fid: ["Advertencia de prueba."]})
    con_fuente = [f for f in fichas.values() if fid in f["fuentes"]]
    assert con_fuente and all(f["fuentes"][fid]["advertencias"] == ["Advertencia de prueba."] for f in con_fuente)
    otras = [r for f in fichas.values() for k, r in f["fuentes"].items() if k != fid]
    assert all("advertencias" not in r for r in otras)  # solo la fuente que las tiene


def test_el_resumen_de_las_advertencias_llega_a_la_web(web):
    """AC-L26 / AC-V23: el resumen visible de la ECH nombra los cuatro temas y llega a fuentes.json y a las
    fichas con datos de esa fuente, junto a las advertencias completas."""
    import re

    fuentes = {f["id"]: f for f in json.loads((web / "fuentes.json").read_text(encoding="utf-8"))}
    ech = "ine_ech_mercado_trabajo_departamental"
    resumen = fuentes[ech]["resumen_advertencias"]
    for tema in (r"lugar de residencia", r"departamentos chicos", r"estacional", r"ranking"):
        assert re.search(tema, resumen), tema
    assert "resumen_advertencias" not in fuentes["ine_unidades_geoestadisticas_2023"]
    for archivo in list((web / "fichas").glob("*/*.json"))[:300]:
        refs = json.loads(archivo.read_text(encoding="utf-8"))["fuentes"]
        if ech in refs:
            assert refs[ech]["resumen_advertencias"] == resumen


# ------------------------------------------------------------------ M11.1: catálogo de niveles (AC-N1…N3)

CAMPOS_NIVEL = {"id", "etiqueta", "ayuda", "orden", "dibujable", "capa", "minzoom", "ambito", "dentro_de"}


def test_catalogo_de_niveles_en_niveles_json(web, territorios):
    """AC-N1: niveles.json lista cada nivel con id, etiqueta, ayuda, orden (de grueso a fino), dibujable, zoom mínimo
    y ámbito. Los dibujables son los de D1 (#200), en el orden de D2."""
    cat = json.loads((web / "niveles.json").read_text(encoding="utf-8"))
    assert all(set(n) == CAMPOS_NIVEL for n in cat)
    assert [n["orden"] for n in cat] == sorted({n["orden"] for n in cat})  # sin repetidos, ya ordenado
    assert set(territorios.nivel) <= {n["id"] for n in cat}  # ningún nivel de la base queda fuera
    dib = [n["id"] for n in cat if n["dibujable"]]
    assert dib == ["departamento", "municipio_mvd", "seccion", "barrio_mvd", "segmento"]
    por_id = {n["id"]: n for n in cat}
    assert por_id["segmento"]["minzoom"] == 9 and por_id["departamento"]["minzoom"] is None
    assert {n["id"] for n in cat if n["ambito"] == "montevideo"} == {"municipio_mvd", "barrio_mvd", "ccz_mvd"}
    assert por_id["municipio_mvd"]["ayuda"] == por_id["barrio_mvd"]["ayuda"] == "Solo Montevideo"
    assert not por_id["localidad"]["dibujable"] and not por_id["ccz_mvd"]["dibujable"]  # D1
    # M11.3: con capa (para resaltar lo elegido) aunque no vayan al selector; región sin geometría, sin capa
    assert por_id["localidad"]["capa"] and por_id["ccz_mvd"]["capa"] and not por_id["region"]["capa"]
    assert all(n["capa"] for n in cat if n["dibujable"])


def test_cada_nivel_del_mapa_tiene_capa_en_el_pmtiles():
    """AC-N1 (`dibujable`): un nivel que D1 pone en el mapa sin capa en el PMTiles hace fallar este test, y el zoom
    mínimo del catálogo es el de la capa."""
    from web import NIVELES_CATALOGO, catalogo_niveles

    sin_capa = [n["id"] for n in NIVELES_CATALOGO if n["en_mapa"] and n["id"] not in PMTILES_MINZOOM]
    assert sin_capa == []
    # un nivel de D1 sin capa nunca se publica como dibujable
    import web

    falso = {"id": "nivel_falso", "etiqueta": "Falso", "en_mapa": True, "ambito": "pais", "dentro_de": []}
    web.NIVELES_CATALOGO.append(falso)
    try:
        assert not next(n for n in catalogo_niveles() if n["id"] == "nivel_falso")["dibujable"]
    finally:
        web.NIVELES_CATALOGO.remove(falso)


def test_niveles_sin_geometria_nunca_son_dibujables():
    """AC-N3: país y región (sin geometría para el mapa) están en el catálogo, pero nunca dibujables."""
    from web import catalogo_niveles

    cat = {n["id"]: n for n in catalogo_niveles()}
    assert {"pais", "region"} <= set(cat) and SIN_GEOMETRIA <= set(cat)
    assert not cat["pais"]["dibujable"] and not any(cat[n]["dibujable"] for n in SIN_GEOMETRIA)


def test_niveles_de_cada_indicador_salen_de_las_observaciones():
    """AC-N2: un indicador lista solo los niveles donde tiene al menos un valor; país y región se listan (las fichas
    los usan) aunque el catálogo no los dibuje."""
    import pandas as pd
    from web import disponibilidad

    terr = pd.DataFrame({"id": ["p", "r", "d1", "s1"], "nivel": ["pais", "region", "departamento", "seccion"]})
    ind = pd.DataFrame({"codigo": ["a", "b"], "tema": ["Población", "Trabajo"], "nombre": ["A", "B"]})
    obs = pd.DataFrame({"indicador": ["a", "a", "b", "b"], "territorio_id": ["d1", "s1", "p", "r"],
                        "periodo": ["2023", "2023", "2024", "2024"], "valor": [1.0, 2.0, 3.0, 4.0]})
    niveles = {f["codigo"]: f["niveles"] for f in disponibilidad(ind, terr, obs)}
    assert niveles == {"a": ["departamento", "seccion"], "b": ["pais", "region"]}


def test_niveles_mapa_pide_al_menos_dos_territorios_con_valor():
    """AC-N6 (#204): un nivel va al mapa del indicador si tiene valor en al menos 2 territorios. Los ingresos de la ECH
    (solo Montevideo por departamento) quedan sin niveles en el mapa; un nivel con un valor nulo no cuenta ese territorio."""
    import pandas as pd
    from web import MIN_TERRITORIOS_MAPA, disponibilidad

    assert MIN_TERRITORIOS_MAPA == 2
    terr = pd.DataFrame({"id": ["p", "d1", "d2", "s1", "s2"], "nivel": ["pais", "departamento", "departamento", "seccion", "seccion"]})
    ind = pd.DataFrame({"codigo": ["ingreso", "educacion"], "tema": ["Ingresos", "Educación"], "nombre": ["I", "E"]})
    obs = pd.DataFrame({
        "indicador": ["ingreso", "ingreso", "educacion", "educacion", "educacion", "educacion"],
        "territorio_id": ["p", "d1", "d1", "d2", "s1", "s2"],
        "periodo": ["2024"] * 6,
        "valor": [10.0, 12.0, 5.0, 6.0, 1.0, None],
    })
    f = {x["codigo"]: x for x in disponibilidad(ind, terr, obs)}
    assert f["ingreso"]["niveles"] == ["departamento", "pais"] and f["ingreso"]["niveles_mapa"] == []
    assert f["educacion"]["niveles_mapa"] == ["departamento"]  # sección: un solo territorio con valor


def test_v33_mapa_solo_si_hay_un_nivel_dibujable_o_comparacion_regional():
    """AC-V33 (#247, V-26): `mapa` queda en true solo si el indicador tiene un nivel dibujable en `niveles_mapa` (AC-N6)
    o se publica por región y va a la comparación regional (AC-I20). Uno de educación con solo el total del país, o
    con un solo departamento, sale del mapa; el `mapa: false` de entrada (#213) no cambia."""
    import pandas as pd
    from web import disponibilidad

    terr = pd.DataFrame({"id": ["p", "r1", "r2", "d1", "d2"], "nivel": ["pais", "region", "region", "departamento", "departamento"]})
    ind = pd.DataFrame({"codigo": ["depto", "pais", "un_depto", "region", "oculto"],
                        "tema": ["Educación", "Educación", "Educación", "Ingresos", "Educación"],
                        "nombre": ["D", "P", "U", "R", "O"], "mapa": [True, True, True, True, False]})
    obs = pd.DataFrame({"indicador": ["depto", "depto", "pais", "un_depto", "un_depto", "region", "region", "oculto", "oculto"],
                        "territorio_id": ["d1", "d2", "p", "p", "d1", "p", "r1", "d1", "d2"],
                        "periodo": ["2024"] * 9, "valor": [1.0] * 9})
    f = {x["codigo"]: x["mapa"] for x in disponibilidad(ind, terr, obs)}
    assert f == {"depto": True, "pais": False, "un_depto": False, "region": True, "oculto": False}


def test_v33_ningun_indicador_del_mapa_queda_sin_nivel_ni_comparacion(web):
    """AC-V33 (#247) sobre el catálogo que genera web.py (fixture y completo): cada indicador con `mapa: true` tiene un
    nivel dibujable en `niveles_mapa` o se publica por región (comparación regional, AC-I20)."""
    from web import catalogo_niveles

    dibujables = {n["id"] for n in catalogo_niveles() if n["dibujable"]}
    ind = json.loads((web / "indicadores.json").read_text(encoding="utf-8"))
    sin_mapa = [i["codigo"] for i in ind
                if i.get("mapa") and not (set(i["niveles_mapa"]) & dibujables or "region" in i["niveles"])]
    assert sin_mapa == [], f"{len(sin_mapa)} indicadores del mapa sin nivel dibujable: {sin_mapa[:5]}"
    assert any(i.get("mapa") for i in ind)


def _registro_mapa(tmp_path, texto):
    p = tmp_path / "indicadores.yml"
    p.write_text(texto, encoding="utf-8")
    return p


REGISTRO_CHICO = """
familias:
  prom:
    nombre_corto: "Promoción en primaria pública"
    aperturas:
      prom_rural: {nombre_corto: "Promoción en primaria pública: rural", apertura: {"Área": "Rural"}}
  priv:
    nombre_corto: "Promoción en primaria privada"
    aperturas:
      priv_m: {nombre_corto: "Promoción en primaria privada: mujeres", apertura: {"Sexo": "Mujeres"}}
fuera_del_mapa:
  prom_repetido: "repite el total"
"""


def test_v34_nombre_familia_y_apertura_salen_del_registro(tmp_path):
    """AC-V34/AC-V35 (#248): cada indicador del mapa toma nombre corto, familia y apertura del registro; los de
    `fuera_del_mapa` y la apertura cuyo total no está en el mapa salen del mapa; los que no van al mapa no se tocan."""
    from web import con_nombres_del_mapa

    filas = [{"codigo": c, "mapa": m} for c, m in
             [("prom", True), ("prom_rural", True), ("prom_repetido", True), ("priv", False), ("priv_m", True), ("otro", False)]]
    r = {f["codigo"]: f for f in con_nombres_del_mapa(filas, _registro_mapa(tmp_path, REGISTRO_CHICO))}
    assert r["prom"] | {} == {"codigo": "prom", "mapa": True, "nombre_corto": "Promoción en primaria pública",
                              "familia": "prom", "apertura": []}
    assert r["prom_rural"]["familia"] == "prom" and r["prom_rural"]["apertura"] == [{"dimension": "Área", "valor": "Rural"}]
    assert r["prom_repetido"]["mapa"] is False and "nombre_corto" not in r["prom_repetido"]
    assert r["priv_m"]["mapa"] is False  # su total (priv) no está en el mapa: la familia no queda sin total (AC-V35)
    assert r["otro"] == {"codigo": "otro", "mapa": False}


def test_v34_un_indicador_del_mapa_sin_registro_frena(tmp_path):
    import pytest
    from web import ErrorRegistroMapa, con_nombres_del_mapa

    with pytest.raises(ErrorRegistroMapa, match="sin nombre corto"):
        con_nombres_del_mapa([{"codigo": "nuevo", "mapa": True}], _registro_mapa(tmp_path, REGISTRO_CHICO))


def test_v34_el_registro_rechaza_nombres_largos_rutas_y_combinaciones_repetidas(tmp_path):
    import pytest
    from web import ErrorRegistroMapa, leer_registro_mapa

    malos = [
        'familias:\n  a:\n    nombre_corto: "' + "x" * 49 + '"\n',
        'familias:\n  a:\n    nombre_corto: "Matrícula / sexo"\n',
        'familias:\n  a:\n    nombre_corto: "Cuadro II-2.2.1"\n',
        'familias:\n  a:\n    nombre_corto: "A"\n    aperturas:\n      b: {nombre_corto: "B", apertura: {"Sexo": "Mujeres"}}\n'
        '      c: {nombre_corto: "C", apertura: {"Sexo": "Mujeres"}}\n',
    ]
    for texto in malos:
        with pytest.raises(ErrorRegistroMapa):
            leer_registro_mapa(_registro_mapa(tmp_path, texto))


def test_v35_en_el_registro_cada_apertura_tiene_a_su_padre_en_la_familia():
    """#248 (P3): una apertura de varias dimensiones está en el mapa solo si su familia tiene la combinación sin la
    última dimensión (administración y grado antes que administración, grado y sexo): los filtros «Ver por» siempre
    tienen un «Todos» que mostrar."""
    from web import leer_registro_mapa

    entradas, _ = leer_registro_mapa()
    combos = {(e["familia"], tuple((a["dimension"], a["valor"]) for a in e["apertura"])) for e in entradas.values()}
    for codigo, e in entradas.items():
        clave = tuple((a["dimension"], a["valor"]) for a in e["apertura"])
        assert not clave or (e["familia"], clave[:-1]) in combos, codigo


def test_v34_v35_los_indicadores_del_mapa_tienen_nombre_familia_y_total(web):
    """AC-V34/AC-V35 (#248) sobre el catálogo que genera web.py (fixture y completo)."""
    ind = json.loads((web / "indicadores.json").read_text(encoding="utf-8"))
    mapa = {i["codigo"]: i for i in ind if i.get("mapa")}
    assert mapa
    familias: dict[str, set] = {}
    for c, i in mapa.items():
        assert 0 < len(i["nombre_corto"]) <= 48 and not any(x in i["nombre_corto"] for x in "/·*"), c
        assert i["familia"] in mapa and mapa[i["familia"]]["apertura"] == [], c  # el total de la familia está en el mapa
        clave = tuple((a["dimension"], a["valor"]) for a in i["apertura"])
        assert clave not in familias.setdefault(i["familia"], set()), c  # combinaciones únicas en la familia
        familias[i["familia"]].add(clave)


def test_dentro_de_nombra_niveles_mas_gruesos_del_catalogo():
    """AC-N7 (#202): `dentro_de` lista solo niveles del catálogo más gruesos que el propio; un barrio no está dentro de
    un municipio (no se contienen exactamente) y el segmento sí está dentro de su sección."""
    from web import catalogo_niveles

    cat = {n["id"]: n for n in catalogo_niveles()}
    for n in cat.values():
        assert all(p in cat and cat[p]["orden"] < n["orden"] for p in n["dentro_de"]), n["id"]
    assert "municipio_mvd" not in cat["barrio_mvd"]["dentro_de"]
    assert {"seccion", "departamento"} <= set(cat["segmento"]["dentro_de"])
