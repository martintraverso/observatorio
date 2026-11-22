"""F3.2 (#126): nivel territorial `region`, sin geometría (AC-I1…AC-I3).

Las tres regiones en las que el INE publica las series de ingresos de la ECH (decisión del mantenedor del
2026-11-19, docs/PLAN_ingresos.md). Corren sobre el fixture o sobre los datos completos (OBS_DATOS=completo).
"""

from __future__ import annotations

import json

import geopandas as gpd
import pytest
from territorios_2023 import SIN_GEOMETRIA as SIN_GEOMETRIA_PIPELINE
from web import SIN_GEOMETRIA

REGIONES = {
    "INE-2023/region/interior": "Interior del país",
    "INE-2023/region/interior-5000": "Interior: localidades de 5.000 o más habitantes",
    "INE-2023/region/interior-menores": "Interior: localidades pequeñas y zonas rurales",
}
PAIS = "INE-2023/pais/UY"
INTERIOR = "INE-2023/region/interior"


def uno(con, sql, params=None):
    return con.execute(sql, params or []).fetchone()[0]


@pytest.fixture(scope="module")
def indice(web):
    return json.loads((web / "territorios_index.json").read_text(encoding="utf-8"))


def ficha(web, nivel, codigo):
    return json.loads((web / "fichas" / nivel / f"{codigo}.json").read_text(encoding="utf-8"))


# AC-I1
def test_tres_regiones_sin_geometria_hijas_del_pais(con, salida):
    filas = con.execute("""select id, nombre, padre_id, area_km2 from territorios
                           where nivel = 'region' order by id""").fetchall()
    assert {i: n for i, n, _, _ in filas} == REGIONES
    assert all(p == PAIS and a is None for _, _, p, a in filas)
    t = gpd.read_parquet(salida / "territorios.parquet").set_index("id")
    assert t.loc[list(REGIONES)].geometry.isna().all()
    # ningún otro nivel queda sin geometría
    assert set(t[t.geometry.isna()].nivel) == SIN_GEOMETRIA == SIN_GEOMETRIA_PIPELINE == {"region"}


# AC-I2
def test_relaciones_de_las_regiones(con):
    rel = con.execute("""select origen_id, destino_id from correspondencias
                         where tipo = 'pertenece_a' and (destino_id like 'INE-2023/region/%'
                                                         or origen_id like 'INE-2023/region/%')""").fetchall()
    rel = set(rel)
    assert ("INE-2023/region/interior-5000", INTERIOR) in rel
    assert ("INE-2023/region/interior-menores", INTERIOR) in rel
    assert (INTERIOR, PAIS) in rel
    deptos = {i for (i,) in con.execute("select id from territorios where nivel = 'departamento'").fetchall()}
    al_interior = {o for o, d in rel if d == INTERIOR and o.startswith("INE-2023/departamento/")}
    assert al_interior == deptos - {"INE-2023/departamento/01"}
    assert len(rel) == len(al_interior) + 3, "ninguna otra relación con las regiones"


def test_cantidad_de_departamentos_del_interior(con, modo):
    n = uno(con, """select count(*) from correspondencias
                    where destino_id = 'INE-2023/region/interior' and origen_id like 'INE-2023/departamento/%'""")
    if modo == "completo":
        assert n == 18


def test_ningun_valor_se_calcula_desde_las_relaciones(con):
    """AC-I2: las relaciones no generan valores. Las regiones solo tienen observaciones de fuentes que publican
    ese nivel (los ingresos de la ECH, F3.4); ninguna otra fuente, ni nada derivado, tiene valores en region."""
    fuentes = {f for (f,) in con.execute("""select distinct c.fuente_id from observaciones o
                                             join territorios t on t.id = o.territorio_id
                                             join capturas c on c.id = o.captura_id where t.nivel = 'region'""").fetchall()}
    assert fuentes <= {"ine_ech_ingresos_series"}
    assert uno(con, """select count(*) from observaciones o join territorios t on t.id = o.territorio_id
                       where t.nivel = 'region' and o.es_estimado""") == 0


# AC-I3
def test_la_web_no_dibuja_las_regiones(web, salida):
    assert not (web / "region.geojson").exists()
    assert not (salida / "descargas" / "territorios_region.parquet").exists()
    assert not (salida / "descargas" / "territorios_region.geojson").exists()
    descargas = json.loads((web / "descargas.json").read_text(encoding="utf-8"))
    assert not any("region" in a["nombre"] for a in descargas["archivos"])


def test_pmtiles_sin_capa_de_regiones(pmtiles):
    from pmtiles.reader import MmapSource, Reader

    with open(pmtiles, "rb") as f:
        meta = Reader(MmapSource(f)).metadata()
    assert "region" not in {c["id"] for c in meta["vector_layers"]}


def test_indice_tiene_las_regiones_sin_caja(indice):
    regiones = {t["id"]: t for t in indice if t["nivel"] == "region"}
    assert set(regiones) == set(REGIONES)
    assert all(t["bbox"] is None and t["padre_id"] == PAIS for t in regiones.values())
    assert regiones[INTERIOR]["nombre_busqueda"] == "interior del pais"


def test_fichas_de_las_regiones(web):
    f = ficha(web, "region", "interior")
    assert f["nombre"] == "Interior del país" and f["bbox"] is None and f["area_km2"] is None
    assert [p["id"] for p in f["padres"]] == [PAIS]
    assert {d["id"] for d in f["contenidos"]["departamento"]} >= {"INE-2023/departamento/07"}
    assert "INE-2023/departamento/01" not in {d["id"] for d in f["contenidos"]["departamento"]}
    assert {r["id"] for r in f["contenidos"]["region"]} == {"INE-2023/region/interior-5000",
                                                           "INE-2023/region/interior-menores"}
    assert {r["destino_id"] for r in f["relaciones"]} == {PAIS}
    # el departamento sabe a qué región pertenece; Montevideo no está en el Interior
    assert {r["destino_id"] for r in ficha(web, "departamento", "07")["relaciones"]} >= {INTERIOR}
    assert INTERIOR not in {r["destino_id"] for r in ficha(web, "departamento", "01")["relaciones"]}
    assert set(r["id"] for r in ficha(web, "pais", "UY")["contenidos"]["region"]) == set(REGIONES)


@pytest.mark.parametrize("codigo", ["interior-5000", "interior-menores"])
def test_subregiones(web, codigo):
    f = ficha(web, "region", codigo)
    assert f["bbox"] is None and [p["id"] for p in f["padres"]] == [PAIS]
    assert {r["destino_id"] for r in f["relaciones"]} == {INTERIOR}


# F3.7a (#148, AC-I22): las fichas fuera de Montevideo saben qué temas tiene el Interior

def _fichas_con_ingresos_en_el_interior(salida):
    """construir_fichas con un valor de ingresos de ejemplo en el Interior (la fuente real está «en preparación»)."""
    import pandas as pd
    from web import construir_fichas

    t = gpd.read_parquet(salida / "territorios.parquet")
    obs = pd.read_parquet(salida / "observaciones.parquet")
    ind = pd.read_parquet(salida / "indicadores.parquet")
    cap = pd.read_parquet(salida / "capturas.parquet")
    ejemplo = obs.head(1).assign(indicador="ing_prueba", territorio_id=INTERIOR, periodo="2026-T3", valor=1.0)
    ind = pd.concat([ind, ind.head(1).assign(codigo="ing_prueba", tema="Ingresos")], ignore_index=True)
    return construir_fichas(t, pd.concat([obs, ejemplo], ignore_index=True), ind, cap,
                            pd.read_parquet(salida / "fuentes.parquet"), pd.read_parquet(salida / "correspondencias.parquet"))


def test_las_fichas_del_interior_llevan_su_region_con_los_temas(salida):
    fichas = _fichas_con_ingresos_en_el_interior(salida)
    flores = fichas["INE-2023/departamento/07"]
    assert flores["region"] == {"id": INTERIOR, "nivel": "region", "codigo": "interior", "nombre": "Interior del país",
                                "temas": ["Ingresos"]}
    seg = next(f for i, f in fichas.items() if i.startswith("INE-2023/segmento/07"))
    assert seg["region"]["id"] == INTERIOR
    # Montevideo, sus unidades, el país y las regiones no llevan región
    assert all("region" not in fichas[i] for i in fichas if fichas[i]["depto"] in ("01", ""))


def test_sin_datos_en_el_interior_la_region_no_trae_temas(web):
    """Con la fuente de ingresos «en preparación» la app no tiene sus valores: ningún enlace a una ficha vacía."""
    import yaml

    from comun.registro import RAIZ

    estado = yaml.safe_load((RAIZ / "fuentes" / "ine_ech_ingresos_series.yml").read_text(encoding="utf-8"))["estado"]
    if estado == "activa":
        pytest.skip("la fuente de ingresos está activa: la región trae sus temas")
    assert ficha(web, "departamento", "07")["region"]["temas"] == []


# F3.7d (#151, AC-I25): el CSV de observaciones trae los ingresos con su período y su base de precios

def test_csv_de_observaciones_con_ingresos(salida):
    """Con los datos reales si ya están (datos completos); si no (fixture), con un valor de ejemplo en el Interior."""
    import pandas as pd
    from web import csv_observaciones

    t = gpd.read_parquet(salida / "territorios.parquet")
    obs = pd.read_parquet(salida / "observaciones.parquet")
    cap = pd.read_parquet(salida / "capturas.parquet")
    ind = pd.read_parquet(salida / "indicadores.parquet")
    codigo = "ing_hogar_medio_sagu_svl"
    ya = (obs.indicador == codigo) & (obs.territorio_id == INTERIOR) & (obs.periodo == "2026-T3")
    if not ya.any():
        ejemplo = obs.head(1).assign(indicador=codigo, territorio_id=INTERIOR, periodo="2026-T3",
                                     periodo_inicio=pd.Timestamp("2026-07-01").date(),
                                     periodo_fin=pd.Timestamp("2026-09-30").date(), tipo_periodo="trimestre", valor=83651.0)
        obs = pd.concat([obs, ejemplo], ignore_index=True)
    if codigo not in set(ind.codigo):
        ind = pd.concat([ind, ind.head(1).assign(codigo=codigo, unidad="pesos corrientes por mes", tema="Ingresos")],
                        ignore_index=True)
    csv = csv_observaciones(t, obs, ind, cap, pd.read_parquet(salida / "fuentes.parquet"))
    fila = csv[(csv.indicador == codigo) & (csv.territorio_id == INTERIOR) & (csv.periodo == "2026-T3")]
    assert len(fila) == 1
    fila = fila.iloc[0]
    assert (fila.nivel, fila.tipo_periodo, fila.periodo_inicio, fila.periodo_fin) == ("region", "trimestre", "2026-07-01", "2026-09-30")
    assert fila.unidad == "pesos corrientes por mes"
