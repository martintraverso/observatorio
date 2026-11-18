"""F2.6 (#45): controles de calidad de la ECH (AC-L12…L16) y su sección del reporte (AC-L21).

Sobre los tres informes de prueba parseados, con alteraciones puntuales para cada control.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from ech_controles import controles, seccion_reporte
from ech_mercado_trabajo import parsear_informe

FIX = Path(__file__).resolve().parent / "fixtures" / "ech_mt"


@pytest.fixture(scope="module")
def obs() -> pd.DataFrame:
    partes = [parsear_informe((FIX / f"ech_mt_{i}.html").read_text(encoding="utf-8")).assign(captura_id=f"c{i}")
              for i in ["2022_02", "2024_09", "2026_09"]]
    return pd.concat(partes, ignore_index=True)


def con_valor(obs, codigo, indicador, valor, periodo="2026-07/2026-09"):
    o = obs.copy()
    fila = (o.territorio_id.str.endswith(f"/{codigo}")) & (o.indicador == indicador) & (o.periodo == periodo)
    assert fila.sum() == 1
    o.loc[fila, "valor"] = valor
    return o


def fallas(obs):
    c, _ = controles(obs)
    return [f["control"] for f in c.fallas]


def test_los_informes_de_prueba_pasan_todos_los_controles(obs):
    c, advertencias = controles(obs)
    assert c.fallas == []
    assert {x["control"][:6] for x in c.lista} >= {"AC-L12", "AC-L13", "AC-L14", "AC-L15", "AC-L16"}
    assert isinstance(advertencias, list)


# AC-L12
def test_tasas_entre_0_y_100_y_empleo_no_mayor_que_actividad(obs):
    assert any(f.startswith("AC-L12") for f in fallas(con_valor(obs, "10", "tasa_desempleo", 101.0)))
    assert any(f.startswith("AC-L12") for f in fallas(con_valor(obs, "10", "tasa_no_registro", -1.0)))
    assert any(f.startswith("AC-L12") for f in fallas(con_valor(obs, "19", "tasa_empleo", 60.0)))  # > 54,1


# AC-L13
def test_activos_menos_ocupados_igual_desocupados(obs):
    assert not fallas(con_valor(obs, "01", "desocupados", 54.1 + 0.9))  # dentro de ±1 mil
    assert any(f.startswith("AC-L13") for f in fallas(con_valor(obs, "01", "desocupados", 54.1 + 1.5)))


# AC-L14 (decisión del mantenedor, opción c: advertencia, no falla)
def test_tasa_de_desempleo_calculada_fuera_de_0_3_es_advertencia(obs):
    # Montevideo 2026: 54,1 / 755,8 × 100 = 7,16 contra 7,2 publicado; con 6,5 la diferencia es 0,66
    o = con_valor(obs, "01", "tasa_desempleo", 6.5)
    c, advertencias = controles(o)
    assert c.fallas == []
    assert any("Montevideo" in a or "departamento/01" in a for a in advertencias)
    assert any(x["control"].startswith("AC-L14") and "1 fuera" in x["detalle"] for x in c.lista)


# AC-L15
def test_territorios_e_indicadores_esperados_por_informe(obs):
    sin_flores = obs[~((obs.territorio_id == "INE-2023/departamento/07") & (obs.periodo == "2024-07/2024-09"))]
    assert any(f.startswith("AC-L15") for f in fallas(sin_flores))
    un_indicador = (obs.territorio_id == "INE-2023/municipio_mvd/CH") & (obs.indicador == "activos") & (
        obs.periodo == "2022-02".replace("2022-02", "2021-12/2022-02"))
    assert un_indicador.sum() == 1
    assert any(f.startswith("AC-L15") for f in fallas(obs[~un_indicador]))
    pais_2026 = obs[(obs.territorio_id == "INE-2023/pais/UY")]
    assert any(f.startswith("AC-L15") for f in fallas(pd.concat([obs, pais_2026.iloc[:1]])))  # repetido


# AC-L16
def test_ningun_valor_en_secciones_segmentos_localidades_barrios_ni_ccz(obs):
    for nivel, codigo in [("seccion", "0701"), ("segmento", "0701001"), ("localidad", "07020"),
                          ("barrio_mvd", "1"), ("ccz_mvd", "01")]:
        extra = obs.iloc[:1].assign(territorio_id=f"INE-2023/{nivel}/{codigo}")
        assert any(f.startswith("AC-L16") for f in fallas(pd.concat([obs, extra]))), nivel


# AC-L21
def test_seccion_del_reporte(obs):
    c, advertencias = controles(obs)
    registro = [{"periodo": p, "vigente": True} for p in sorted(set(obs.periodo))]
    texto = "\n".join(seccion_reporte(obs, registro, c, advertencias, redondeo=[]))
    assert "## Mercado de trabajo (ECH)" in texto
    assert "Meses capturados: 3" in texto and "faltan" in texto  # entre 2022-02 y 2026-09 faltan meses
    assert "| AC-L12" in texto and "| AC-L16" in texto
    assert "Últimos valores por departamento (2026-07/2026-09)" in texto
    assert "| Treinta y Tres | 54,1 | 48,6 | 10,2 |" in texto
