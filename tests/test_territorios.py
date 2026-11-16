"""Pruebas sobre la salida del pipeline de territorios (AC-T1…T9, AC-P3, AC-P4, AC-P5).

Corren sobre el fixture (por defecto) o sobre los datos completos (OBS_DATOS=completo).
Ver tests/conftest.py.
"""

import re

import geopandas as gpd
import pyogrio
import pytest

INDICADORES = ["pob_total", "pob_hombres", "pob_mujeres", "viviendas_total"]


def uno(con, sql, params=None):
    return con.execute(sql, params or []).fetchone()[0]


# AC-T1
def test_cantidades_por_nivel(con, esperado):
    conteo = dict(con.execute("select nivel, count(*) from territorios group by nivel").fetchall())
    assert conteo == esperado["territorios_por_nivel"]


# AC-T2
def test_ids_unicos_y_con_formato(con):
    assert uno(con, "select count(*) - count(distinct id) from territorios") == 0
    filas = con.execute("select id, nivel, codigo from territorios").fetchall()
    patron = re.compile(r"^INE-2023/[a-z_]+/[0-9A-Za-z-]+$")
    malos = [i for i, nivel, codigo in filas if i != f"INE-2023/{nivel}/{codigo}" or not patron.match(i)]
    assert malos == []


# AC-T3
def test_geometrias_validas_y_no_vacias(salida):
    t = gpd.read_parquet(salida / "territorios.parquet")
    assert t.geometry.notna().all()
    assert t.geometry.is_valid.all(), t.loc[~t.geometry.is_valid, "id"].tolist()[:5]
    assert (~t.geometry.is_empty).all(), t.loc[t.geometry.is_empty, "id"].tolist()[:5]


# AC-T4
def test_todo_padre_existe(con):
    assert uno(con, """
        select count(*) from territorios h
        where h.padre_id is not null and h.padre_id not in (select id from territorios)
    """) == 0


def test_jerarquia_por_prefijo(con):
    # Toda sección y todo segmento empieza con el código de su departamento.
    assert uno(con, """
        select count(*) from territorios
        where nivel in ('seccion','segmento') and substr(codigo, 1, 2) <> depto
    """) == 0
    # La sección cuelga de su departamento; el segmento, de la sección con la que empieza su código.
    assert uno(con, """
        select count(*) from territorios
        where (nivel = 'seccion' and padre_id <> 'INE-2023/departamento/' || depto)
           or (nivel = 'segmento' and padre_id <> 'INE-2023/seccion/' || substr(codigo, 1, 4))
    """) == 0


def test_segmento_ejemplo_del_ine(con, modo):
    if modo != "completo":
        pytest.skip("El segmento 1605601 (San José) no está en el fixture")
    # El código de ejemplo de la documentación del INE (zona 1605601031) pertenece a este segmento.
    padre = uno(con, "select padre_id from territorios where nivel='segmento' and codigo='1605601'")
    assert padre == "INE-2023/seccion/1605"


# AC-T5
def test_codigos_departamento_ine(con):
    assert uno(con, "select nombre from territorios where nivel='departamento' and codigo='01'") == "Montevideo"
    assert uno(con, "select nombre from territorios where nivel='departamento' and codigo='16'") == "San José"


# AC-T6
def test_suma_de_segmentos_igual_a_seccion(con):
    distintos = con.execute("""
        with seg as (
          select t.padre_id as seccion_id, o.indicador, sum(o.valor) as suma
          from observaciones o join territorios t on t.id = o.territorio_id
          where t.nivel = 'segmento' group by all
        )
        select o.territorio_id, o.indicador, o.valor, seg.suma
        from observaciones o
        join territorios t on t.id = o.territorio_id and t.nivel = 'seccion'
        left join seg on seg.seccion_id = o.territorio_id and seg.indicador = o.indicador
        where seg.suma is distinct from o.valor
    """).fetchall()
    assert distintos == []
    indicadores = {r[0] for r in con.execute("""
        select distinct indicador from observaciones o join territorios t on t.id = o.territorio_id
        where t.nivel = 'seccion'
    """).fetchall()}
    assert indicadores == set(INDICADORES)


# AC-T7
def test_hombres_mas_mujeres(con):
    assert uno(con, """
        select count(*) from (
          pivot observaciones on indicador using first(valor) group by territorio_id
        ) where pob_hombres + pob_mujeres <> pob_total
    """) == 0


# AC-T8
def test_limite_contestado_es_area_especial_sin_observaciones(con):
    filas = con.execute("""
        select id, nivel, depto, padre_id from territorios where codigo = '02-limite-contestado'
    """).fetchall()
    assert filas == [("INE-2023/area_especial/02-limite-contestado", "area_especial", "02",
                      "INE-2023/departamento/02")]
    assert uno(con, """
        select count(*) from observaciones o join territorios t on t.id = o.territorio_id
        where t.nivel = 'area_especial'
    """) == 0
    assert uno(con, "select count(*) from observaciones where territorio_id like '%limite-contestado%'") == 0


# AC-T9
def test_poblacion_departamento_es_la_publicada_por_el_ine(con, entrada, esperado):
    suma_deptos = uno(con, """
        select sum(valor) from observaciones o join territorios t on t.id = o.territorio_id
        where t.nivel = 'departamento' and o.indicador = 'pob_total'
    """)
    suma_secciones = uno(con, """
        select sum(valor) from observaciones o join territorios t on t.id = o.territorio_id
        where t.nivel = 'seccion' and o.indicador = 'pob_total'
    """)
    assert suma_deptos == esperado["pob_total_departamentos"]
    assert suma_secciones == esperado["pob_total_secciones"]
    assert suma_deptos != suma_secciones  # no se agrega hacia arriba

    # Cada departamento tiene exactamente el valor de la capa depto_23_pg del original.
    if not entrada.exists():
        pytest.skip(f"No está el original {entrada.name} para comparar departamento por departamento")
    capa = pyogrio.read_dataframe(f"/vsizip/{entrada}/depto_23_pg.gpkg", read_geometry=False)
    ine = {r.DEPTO: float(r.POB_TOT_23) for r in capa.itertuples() if r.NOMDEPTO != "LIMITE CONTESTADO"}
    guardado = dict(con.execute("""
        select t.codigo, o.valor from observaciones o join territorios t on t.id = o.territorio_id
        where t.nivel = 'departamento' and o.indicador = 'pob_total'
    """).fetchall())
    assert guardado == ine


# AC-P3
def test_cada_observacion_tiene_captura(con):
    assert uno(con, """
        select count(*) from observaciones o left join capturas c on c.id = o.captura_id where c.id is null
    """) == 0
    assert uno(con, """
        select count(*) from capturas
        where coalesce(sha256, '') = '' or coalesce(archivo, '') = ''
    """) == 0


# AC-P4
def test_cada_observacion_tiene_territorio(con):
    assert uno(con, """
        select count(*) from observaciones o left join territorios t on t.id = o.territorio_id where t.id is null
    """) == 0


# AC-P5
def test_observaciones_solo_en_niveles_publicados(con):
    fuera = con.execute("""
        select t.nivel, count(*) from observaciones o
        join territorios t on t.id = o.territorio_id
        join capturas c on c.id = o.captura_id
        join fuentes f on f.id = c.fuente_id
        where not list_contains(f.niveles_publicados, t.nivel) and not o.es_estimado
        group by all
    """).fetchall()
    assert fuera == []


def test_correspondencias_sin_territorio_son_solo_rural_o_especiales(con):
    """Segmento -> localidad sale del atributo CODLOC del INE. Hay códigos sin polígono de localidad:
    XX900 = parte rural del departamento (NOMLOC 'RURAL') y XX000 = islas y límite contestado.
    Se guardan como los publica el INE; ningún otro código puede quedar sin territorio."""
    sin_territorio = [r[0] for r in con.execute("""
        select distinct destino_id from correspondencias
        where destino_id not in (select id from territorios)
    """).fetchall()]
    assert all(re.fullmatch(r"INE-2023/localidad/\d\d(900|000)", d) for d in sin_territorio), sin_territorio
    assert uno(con, "select count(*) from correspondencias where origen_id not in (select id from territorios)") == 0
