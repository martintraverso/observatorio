"""F4.7a (#191): la educación en los datos de la web (AC-E28, AC-E31). Sobre una carga del MEC con los fixtures,
armando las fichas y el CSV con todas las fuentes (la del MEC sigue «en preparación»: en la app publicada no aparece
hasta que se active)."""

from __future__ import annotations

import pandas as pd
import pytest
from test_mec_cargar import correr, entorno  # noqa: F401
from web import con_cuadro, construir_fichas, csv_observaciones

FLORES, PAIS = "INE-2023/departamento/07", "INE-2023/pais/UY"


@pytest.fixture
def web(entorno):  # noqa: F811
    import geopandas as gpd

    crudo, salida = entorno
    correr(crudo, salida)
    t = gpd.read_parquet(salida / "territorios.parquet")
    tablas = {n: pd.read_parquet(salida / f"{n}.parquet") for n in ("observaciones", "indicadores", "capturas", "fuentes", "correspondencias")}
    ind = con_cuadro(tablas["indicadores"])
    fichas = construir_fichas(t, tablas["observaciones"], ind, tablas["capturas"], tablas["fuentes"], tablas["correspondencias"])
    csv = csv_observaciones(t, tablas["observaciones"], ind, tablas["capturas"], tablas["fuentes"])
    return fichas, csv, t


def test_la_ficha_del_departamento_trae_la_educacion_con_su_cuadro(web):
    fichas, _, _ = web
    f = fichas[FLORES]
    edu = [o for o in f["observaciones"] if o["indicador"].startswith("edu_")]
    assert {o["periodo"] for o in edu} >= {"2023", "2024"} and all(o["tipo_periodo"] == "anio" for o in edu)
    i = f["indicadores"]["edu_ii_2_2_1_total"]
    assert i["tema"] == "Educación" and i["cuadro"] == "II-2.2.1" and i["es_derivado"] is False and i["nota"]
    tasa = f["indicadores"]["edu_ii_2_2_13_rendimiento_escolar_tasa_promocion_total"]
    assert tasa["es_derivado"] is True and tasa["formula"] and tasa["cuadro"] == "II-2.2.13" and tasa["unidad"] == "%"


def test_ac_e28_por_debajo_de_departamento_la_educacion_se_ve_como_dato_del_departamento(web):
    """Patrón AC-V24: la ficha de un segmento no tiene valores de educación propios, pero sabe (por su departamento)
    que el tema existe, para decir «Educación: datos por departamento» con el enlace a la ficha del departamento."""
    fichas, _, t = web
    seg = next(i for i in t[t.nivel == "segmento"].id if i.startswith("INE-2023/segmento/07"))
    f = fichas[seg]
    assert not any(o["indicador"].startswith("edu_") for o in f["observaciones"])
    depto = next(p for p in f["padres"] if p["nivel"] == "departamento")
    assert depto["id"] == FLORES and any(k.startswith("edu_") for k in depto["valores"])
    assert any(i["tema"] == "Educación" for k, i in f["indicadores"].items() if k.startswith("edu_"))


def test_la_region_del_interior_lista_educacion_entre_sus_temas(web):
    fichas, _, _ = web
    assert "Educación" in fichas[FLORES]["region"]["temas"]


def test_ac_e31_el_csv_trae_las_filas_de_educacion_con_cuadro_y_es_derivado(web):
    _, csv, _ = web
    edu = csv[csv.indicador.str.startswith("edu_")]
    fila = edu[(edu.territorio_id == FLORES) & (edu.indicador == "edu_ii_2_2_1_total") & (edu.periodo == "2024")].iloc[0]
    assert (fila.tipo_periodo, fila.periodo_inicio, fila.periodo_fin) == ("anio", "2024-01-01", "2024-12-31")
    assert (fila.unidad, fila.cuadro, fila.es_derivado) == ("estudiantes", "II-2.2.1", "false")
    tasa = edu[edu.indicador == "edu_ii_2_2_13_rendimiento_escolar_tasa_promocion_total"].iloc[0]
    assert (tasa.unidad, tasa.cuadro, tasa.es_derivado) == ("%", "II-2.2.13", "true")
    serie = edu[edu.indicador == "edu_serie_total_sistema"]
    assert set(serie.territorio_id) == {PAIS} and (serie.cuadro == "").all()  # la serie nacional no es un cuadro
    otras = csv[~csv.indicador.str.startswith("edu_")]
    assert (otras.cuadro == "").all() and (otras.es_derivado == "false").all()
