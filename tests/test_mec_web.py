"""F4.7a (#191): la educación en los datos de la web (AC-E28, AC-E31). Sobre una carga del MEC con los fixtures,
armando las fichas y el CSV con todas las fuentes (la del MEC sigue «en preparación»: en la app publicada no aparece
hasta que se active)."""

from __future__ import annotations

import pandas as pd
import pytest
from test_mec_cargar import correr, entorno  # noqa: F401
from web import catalogo_educacion, con_corte, con_cuadro, con_mapa, construir_fichas, csv_observaciones

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
    """Patrón AC-V24 (los datos; el texto «Educación: datos por departamento» lo muestra la app, F4.7b #192): las
    fichas de sección, segmento, localidad, barrio y CCZ no tienen valores de educación propios, pero saben por su
    departamento que el tema existe, con el enlace a esa ficha."""
    fichas, _, t = web
    for nivel in ("seccion", "segmento", "localidad", "barrio_mvd", "ccz_mvd"):
        ids = list(t[t.nivel == nivel].id)
        assert ids, nivel
        for i in ids:
            f = fichas[i]
            assert not any(o["indicador"].startswith("edu_") for o in f["observaciones"]), i
            depto = next(p for p in f["padres"] if p["nivel"] == "departamento")
            assert any(k.startswith("edu_") for k in depto["valores"]), i
            assert any(m["tema"] == "Educación" for k, m in f["indicadores"].items() if k.startswith("edu_")), i


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


def test_211_corte_marca_los_indicadores_que_cambian_de_concepto():
    """AC-E13/AC-E30 (#211): los ids que el registro marca «concepto distinto (AC-E13)» llevan su motivo en `corte`
    (la ficha corta la serie ahí); los demás, vacío. No sale del registro de la base: solo de la web."""
    ind = pd.DataFrame({"codigo": ["edu_ii_2_2_1_forma_de_administracion_total_varon", "edu_ii_2_2_1_total", "pob_total"]})
    c = dict(zip(ind.codigo, con_corte(ind).corte))
    assert "2024 esta columna cambia de significado" in c["edu_ii_2_2_1_forma_de_administracion_total_varon"]
    assert c["edu_ii_2_2_1_total"] == "" and c["pob_total"] == ""


def test_211_la_ficha_lleva_el_corte_de_cada_indicador(entorno):  # noqa: F811
    import geopandas as gpd

    crudo, salida = entorno
    correr(crudo, salida)
    t = gpd.read_parquet(salida / "territorios.parquet")
    tablas = {n: pd.read_parquet(salida / f"{n}.parquet") for n in ("observaciones", "indicadores", "capturas", "fuentes", "correspondencias")}
    ind = con_corte(con_cuadro(tablas["indicadores"]))
    fichas = construir_fichas(t, tablas["observaciones"], ind, tablas["capturas"], tablas["fuentes"], tablas["correspondencias"])
    f = fichas[FLORES]
    assert all("corte" in i for i in f["indicadores"].values())


def test_213_mapa_y_grupo_de_cada_indicador():
    """#213: de educación van a la lista del mapa solo las tasas calculadas, con su nivel educativo; los demás temas,
    todos y sin grupo."""
    ind = pd.DataFrame({
        "codigo": ["edu_ii_2_2_13_rendimiento_escolar_tasa_promocion_total", "edu_ii_2_2_1_total", "edu_ii_3_2_11_x_tasa_promocion", "pob_total"],
        "tema": ["Educación", "Educación", "Educación", "Población"],
        "columna_origen": ["Cuadro II-2.2.13 (calculado)", "Cuadro II-2.2.1 · TOTAL", "Cuadro II-3.2.11 (calculado)", ""],
        "es_derivado": [True, False, True, False],
    })
    r = con_mapa(ind).set_index("codigo")
    assert r.mapa.tolist() == [True, False, True, True]
    assert r.grupo.tolist() == ["Primaria", "Primaria", "Media básica", ""]


def test_ac_e32_el_catalogo_lista_cada_cuadro_con_datos(entorno):  # noqa: F811
    """AC-E32 (#226): el catálogo de educación lista cada cuadro con datos, con código, título legible, tipo, años y
    la tasa del mapa si la tiene; sin datos de educación, vacío."""
    crudo, salida = entorno
    correr(crudo, salida)
    obs = pd.read_parquet(salida / "observaciones.parquet")
    ind = pd.read_parquet(salida / "indicadores.parquet")
    cat = {c["cuadro"]: c for c in catalogo_educacion(ind, obs)}
    assert {"II-2.2.1", "II-2.2.13"} <= set(cat)
    c = cat["II-2.2.13"]
    assert c["tipo"] == "A" and c["anios"] == sorted(c["anios"]) and c["titulo"][0].isupper() and not c["titulo"].isupper()
    assert c["mapa"] and "tasa_promocion" in c["mapa"]
    assert cat["II-2.2.1"]["mapa"] == "edu_ii_2_2_1_pct_privada"
    assert all(set(x) == {"cuadro", "titulo", "tipo", "anios", "mapa"} for x in cat.values())
    assert catalogo_educacion(ind[ind.fuente_id != "mec_anuario_educacion"], obs) == []
