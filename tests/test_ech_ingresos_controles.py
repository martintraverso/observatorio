"""F3.5 (#129): controles de calidad de las series de ingresos (AC-I12…AC-I17), sobre los fixtures de F3.1."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from ech_ingresos import parsear_serie
from ech_ingresos_controles import controles, ultimos_valores

FIX = Path(__file__).resolve().parent / "fixtures" / "ech_ingresos"
PAIS, MVD = "INE-2023/pais/UY", "INE-2023/departamento/01"
INTERIOR = "INE-2023/region/interior"


@pytest.fixture(scope="module")
def obs():
    """ECHING07 (con aguinaldo, con valor locativo) y ECHING09 (con aguinaldo, sin valor locativo), hogares."""
    return pd.concat([parsear_serie((FIX / f"{c}.xlsx").read_bytes(), c) for c in ("ECHING07", "ECHING09")],
                     ignore_index=True)


def fallas(df):
    c, _ = controles(df)
    return {f["control"].split(" ")[0] + " " + f["control"].split(" ", 2)[1] for f in c.fallas}, c


def cambiar(df, indicador, territorio, periodo, valor):
    df = df.copy()
    df.loc[(df.indicador == indicador) & (df.territorio_id == territorio) & (df.periodo == periodo), "valor"] = valor
    return df


def test_los_datos_publicados_pasan(obs):
    c, advertencias = controles(obs)
    assert c.fallas == [] and advertencias == []
    assert len(c.lista) >= 7


def test_ac_i12_valores_positivos(obs):
    nombres, _ = fallas(cambiar(obs, "ing_hogar_medio_cagu_cvl", PAIS, "2016-T1", 0.0))
    assert any(n.startswith("AC-I12") for n in nombres)


def test_ac_i13_con_valor_locativo_no_menor_que_sin(obs):
    df = cambiar(obs, "ing_hogar_medio_cagu_cvl", MVD, "2020-T2", 1000.0)  # con vl < sin vl
    c, _ = controles(df)
    # (Montevideo en 1.000 también deja al país fuera de su rango: AC-I14 lo marca, y está bien)
    assert "AC-I13 Con valor locativo ≥ sin valor locativo" in [f["control"] for f in c.fallas]


def test_ac_i13_per_capita_menor_que_hogar():
    k = ["indicador", "territorio_id", "periodo", "tipo_periodo"]
    df = pd.DataFrame([["ing_hogar_medio_sagu_svl", PAIS, "2016-T1", "trimestre", 100.0],
                       ["ing_pc_medio_sagu_svl", PAIS, "2016-T1", "trimestre", 120.0]], columns=[*k, "valor"])
    c, _ = controles(df)
    assert "AC-I13 Per cápita menor que hogar" in [f["control"] for f in c.fallas]


def test_ac_i14_interior_entre_sus_partes_y_pais_entre_mvd_e_interior(obs):
    c, _ = controles(cambiar(obs, "ing_hogar_medio_cagu_svl", INTERIOR, "2019", 1.0))
    assert [f["control"] for f in c.fallas] == ["AC-I14 El Interior está entre sus dos partes"]
    c, _ = controles(cambiar(obs, "ing_hogar_medio_cagu_svl", PAIS, "2019", 999999.0))
    assert "AC-I14 El país está entre Montevideo y el Interior" in [f["control"] for f in c.fallas]


def test_ac_i15_total_lejos_del_promedio_es_advertencia(obs):
    df = cambiar(obs, "ing_hogar_medio_cagu_cvl", PAIS, "2018", 80000.0)  # promedio ~67.725
    c, advertencias = controles(df)
    assert not any("AC-I15" in f["control"] for f in c.fallas)
    assert len(advertencias) == 1 and "2018" in advertencias[0]


def test_ac_i16_falta_un_trimestre_o_un_total(obs):
    sin_t3 = obs[~((obs.indicador == "ing_hogar_medio_cagu_cvl") & (obs.territorio_id == MVD) & (obs.periodo == "2019-T3"))]
    assert any(n.startswith("AC-I16") for n in fallas(sin_t3)[0])
    sin_total = obs[~((obs.periodo == "2020") & (obs.territorio_id == PAIS))]
    assert any(n.startswith("AC-I16") for n in fallas(sin_total)[0])
    # el año en curso (2026) tiene sus tres trimestres y ningún total: está bien
    assert "2026" not in set(obs.periodo) and {"2026-T1", "2026-T2", "2026-T3"} <= set(obs.periodo)
    con_total = pd.concat([obs, obs[obs.periodo == "2025"].assign(periodo="2026")])
    assert any(n.startswith("AC-I16") for n in fallas(con_total)[0])


def test_ac_i17_ningun_departamento_salvo_montevideo(obs):
    otro = obs.head(1).assign(territorio_id="INE-2023/departamento/07")
    seccion = obs.head(1).assign(territorio_id="INE-2023/seccion/0701")
    for extra in (otro, seccion):
        assert any(n.startswith("AC-I17") for n in fallas(pd.concat([obs, extra]))[0])


def test_ultimos_valores_del_titular():
    df = parsear_serie((FIX / "ECHING07.xlsx").read_bytes(), "ECHING07").assign(indicador="ing_hogar_medio_sagu_svl")
    lineas = ultimos_valores(df)
    assert "2026-T3" in lineas[0] and any(lin.startswith("| Total país | 121.188 |") for lin in lineas)
