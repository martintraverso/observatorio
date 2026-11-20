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
    """AC-I2: las relaciones no generan valores. Las regiones no tienen observaciones de ninguna fuente que
    no las publique (hoy, ninguna: los ingresos llegan en F3.4)."""
    assert uno(con, """select count(*) from observaciones o join territorios t on t.id = o.territorio_id
                       where t.nivel = 'region'""") == 0


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
