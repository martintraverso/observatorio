"""F4.2 (#165, AC-E3): el catálogo de indicadores tiene `es_derivado` (bool) y `formula` (texto, vacío para los
valores publicados), para las tasas que calcula el observatorio (decisión D2 de F4)."""

from __future__ import annotations

import pandas as pd
import pytest

from comun.salida import COLUMNAS_INDICADOR, ErrorCombinar, completar_indicadores, escribir_fuente


def indicador(**extra):
    return {"codigo": "x_total", "nombre": "X", "unidad": "personas", "tema": "T", "columna_origen": "A",
            "fuente_id": "f", "nota": "", **extra}


def test_el_catalogo_tiene_es_derivado_y_formula():
    assert {"es_derivado", "formula"} <= set(COLUMNAS_INDICADOR)


def test_un_indicador_publicado_no_es_derivado_y_no_tiene_formula():
    ind = completar_indicadores(pd.DataFrame([indicador()]))
    assert ind.es_derivado.tolist() == [False]
    assert ind.formula.tolist() == [""]
    assert ind.es_derivado.dtype == bool


def test_un_indicador_derivado_conserva_su_formula():
    ind = completar_indicadores(pd.DataFrame([
        indicador(),
        indicador(codigo="x_tasa", unidad="%", es_derivado=True, formula="x_promovidos / (x_promovidos + x_no_promovidos) * 100"),
    ]))
    assert ind.es_derivado.tolist() == [False, True]
    assert ind.formula.tolist()[1].startswith("x_promovidos /")


def test_una_salida_anterior_sin_las_columnas_se_completa(tmp_path):
    obs = pd.DataFrame(columns=["indicador", "territorio_id", "periodo", "periodo_inicio", "periodo_fin",
                                "tipo_periodo", "valor", "es_estimado", "captura_id"])
    d = escribir_fuente(tmp_path, "f", obs, [], pd.DataFrame([indicador()]))
    ind = pd.read_parquet(d / "indicadores.parquet")
    assert ind[["es_derivado", "formula"]].values.tolist() == [[False, ""]]


@pytest.mark.parametrize("extra", [
    {"es_derivado": "false"},  # texto: con astype(bool) sería True
    {"es_derivado": True},  # derivado sin fórmula
    {"es_derivado": False, "formula": "a / b"},  # publicado con fórmula
])
def test_es_derivado_y_formula_tienen_que_ser_coherentes(extra):
    with pytest.raises(ErrorCombinar):
        completar_indicadores(pd.DataFrame([indicador(**extra)]))
