"""Pruebas sobre la salida de la fase 0.

Correr después del pipeline:
  python pipeline/territorios_2023.py RUTA_AL_ZIP
  pytest -q
"""

from pathlib import Path

import duckdb
import pytest

DB = Path(__file__).resolve().parents[1] / "datos" / "salida" / "observatorio.duckdb"

pytestmark = pytest.mark.skipif(not DB.exists(), reason="Primero correr el pipeline")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


def uno(con, sql):
    return con.execute(sql).fetchone()[0]


def test_cantidades_por_nivel(con):
    esperado = {"departamento": 19, "seccion": 236, "segmento": 4538, "localidad": 652,
                "barrio_mvd": 63, "ccz_mvd": 18}
    for nivel, n in esperado.items():
        assert uno(con, f"select count(*) from territorios where nivel = '{nivel}'") == n, nivel


def test_codigos_departamento_ine(con):
    assert uno(con, "select nombre from territorios where nivel='departamento' and codigo='01'") == "Montevideo"
    assert uno(con, "select nombre from territorios where nivel='departamento' and codigo='16'") == "San José"


def test_jerarquia_por_prefijo(con):
    # Una zona/segmento/sección siempre empieza con el código de su departamento.
    malos = uno(con, """
        select count(*) from territorios
        where nivel in ('seccion','segmento') and substr(codigo, 1, 2) <> depto
    """)
    assert malos == 0


def test_segmento_ejemplo_del_ine(con):
    # El código de ejemplo de la documentación del INE (zona 1605601031) pertenece a este segmento.
    padre = uno(con, "select padre_id from territorios where nivel='segmento' and codigo='1605601'")
    assert padre == "INE-2023/seccion/1605"


def test_sin_limite_contestado_en_observaciones(con):
    assert uno(con, "select count(*) from observaciones where territorio_id like '%limite-contestado%'") == 0


def test_cada_observacion_tiene_captura(con):
    assert uno(con, "select count(*) from observaciones o left join capturas c on c.id = o.captura_id where c.id is null") == 0


def test_hombres_mas_mujeres(con):
    assert uno(con, """
        select count(*) from (
          pivot observaciones on indicador using first(valor) group by territorio_id
        ) where pob_hombres + pob_mujeres <> pob_total
    """) == 0
