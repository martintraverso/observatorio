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


# AC-L10 (esquema) y AC-L11
def test_observaciones_tienen_inicio_fin_y_tipo_de_periodo(con):
    tipos = dict(con.execute("select column_name, data_type from information_schema.columns "
                             "where table_name = 'observaciones'").fetchall())
    assert tipos["periodo_inicio"] == "DATE" and tipos["periodo_fin"] == "DATE" and tipos["tipo_periodo"] == "VARCHAR"
    assert uno(con, """select count(*) from observaciones where periodo_inicio is null or periodo_fin is null
                       or tipo_periodo is null or periodo_inicio > periodo_fin""") == 0
    assert uno(con, """select count(*) from observaciones where tipo_periodo not in
                       ('censo','mes','trimestre_movil','trimestre','semestre','anio')""") == 0
    assert "periodo_inicio" in [r[0] for r in con.execute("describe v_observaciones").fetchall()]


def test_censo_migrado_a_tipo_censo(con):
    fuera = con.execute("""
        select tipo_periodo, periodo, periodo_inicio, periodo_fin, count(*) from observaciones o
        join capturas c on c.id = o.captura_id
        where c.fuente_id = 'ine_unidades_geoestadisticas_2023' group by all
    """).fetchall()
    import datetime as dt
    assert [f[:4] for f in fuera] == [("censo", "2023", dt.date(2023, 1, 1), dt.date(2023, 1, 1))]


# ------------------------------------------------------------------ niveles país y municipio (F2.3)

LETRAS_MUNICIPIOS = ["A", "B", "C", "CH", "D", "E", "F", "G"]


def _area(geom) -> float:
    """Área en km² (UTM 21S), para comparar uniones."""
    return float(gpd.GeoSeries([geom], crs=4326).to_crs(32721).area.iloc[0]) / 1e6


def _dif_relativa(a, b) -> float:
    return _area(a.symmetric_difference(b)) / _area(b)


# AC-L17
def test_municipios_de_montevideo(con, salida):
    filas = con.execute("""select codigo, id, padre_id, depto, nombre from territorios
                           where nivel = 'municipio_mvd' order by codigo""").fetchall()
    assert [f[0] for f in filas] == sorted(LETRAS_MUNICIPIOS)
    assert all(i == f"INE-2023/municipio_mvd/{c}" and p == "INE-2023/departamento/01" and d == "01"
               and n == f"Municipio {c}" for c, i, p, d, n in filas)
    t = gpd.read_parquet(salida / "territorios.parquet").set_index("id")
    corr = con.execute("""select origen_id, destino_id from correspondencias
                          where destino_id like 'INE-2023/municipio_mvd/%'""").fetchall()
    for _, municipio, *_ in filas:
        ccz = [o for o, d in corr if d == municipio]
        assert ccz, municipio
        assert _dif_relativa(t.loc[municipio].geometry, t.loc[ccz].geometry.union_all()) < 1e-3, municipio
        # La superficie publicada es la de la geometría (el AREA_KM2 de los CCZ del INE no está en km²).
        assert t.loc[municipio].area_km2 == pytest.approx(_area(t.loc[municipio].geometry), rel=0.01), municipio
    assert sum(t.loc[i].area_km2 for _, i, *_ in filas) < t.loc["INE-2023/departamento/01"].area_km2 * 1.01


# AC-L18
def test_cada_ccz_en_exactamente_un_municipio(con, salida):
    assert uno(con, """
        select count(*) from (
          select c.id, count(r.destino_id) n from territorios c
          left join correspondencias r on r.origen_id = c.id and r.destino_id like 'INE-2023/municipio_mvd/%'
                                        and r.tipo = 'pertenece_a'
          where c.nivel = 'ccz_mvd' group by c.id) where n <> 1
    """) == 0
    # El municipio sale del atributo NOMMUNICIPIO del INE, el mismo que da el nombre del CCZ.
    assert uno(con, """
        select count(*) from correspondencias r join territorios c on c.id = r.origen_id
        where r.destino_id like 'INE-2023/municipio_mvd/%'
          and c.nombre not like '%(Municipio ' || split_part(r.destino_id, '/', 3) || ')'
    """) == 0
    assert con.execute("""select distinct metodo from correspondencias
                          where destino_id like 'INE-2023/municipio_mvd/%'""").fetchall() == [
        ("disolución de CCZ por NOMMUNICIPIO",)]  # SYSTEM.md §5
    t = gpd.read_parquet(salida / "territorios.parquet")
    municipios = t[t.nivel == "municipio_mvd"].geometry.union_all()
    ccz = t[t.nivel == "ccz_mvd"].geometry.union_all()
    assert _dif_relativa(municipios, ccz) < 1e-3


# AC-L28
def test_nivel_pais(con, salida, esperado):
    filas = con.execute("select id, codigo, nombre, padre_id from territorios where nivel = 'pais'").fetchall()
    assert filas == [("INE-2023/pais/UY", "UY", "Uruguay", None)]
    t = gpd.read_parquet(salida / "territorios.parquet").set_index("id")
    deptos = t[t.nivel == "departamento"]
    assert len(deptos) == esperado["territorios_por_nivel"]["departamento"]
    assert _dif_relativa(t.loc["INE-2023/pais/UY"].geometry, deptos.geometry.union_all()) < 1e-3
    assert t.loc["INE-2023/pais/UY"].area_km2 == pytest.approx(_area(t.loc["INE-2023/pais/UY"].geometry), rel=0.01)
    # Cada departamento pertenece al país (relación, no suma de valores).
    assert uno(con, """select count(*) from correspondencias
                       where destino_id = 'INE-2023/pais/UY' and tipo = 'pertenece_a'""") == len(deptos)
    # El Censo no publica en estos niveles: ninguna observación suya, y nada derivado sumando. (La ECH sí
    # publica país y municipios: sus valores están en esos niveles, ver test_ech_cargar.py.)
    assert uno(con, """select count(*) from observaciones o join territorios t on t.id = o.territorio_id
                       join capturas c on c.id = o.captura_id
                       where t.nivel in ('pais', 'municipio_mvd')
                         and c.fuente_id = 'ine_unidades_geoestadisticas_2023'""") == 0


# F2.5b (#57): capturas con URL, fecha de descarga y vigencia
def test_capturas_tienen_url_descargado_y_vigente(con):
    from comun.registro import RAIZ, cargar_fuentes

    cols = dict(con.execute("select column_name, data_type from information_schema.columns "
                            "where table_name = 'capturas'").fetchall())
    assert {"url": "VARCHAR", "descargado": "VARCHAR", "vigente": "BOOLEAN"}.items() <= cols.items()
    url = cargar_fuentes(RAIZ / "fuentes")["ine_unidades_geoestadisticas_2023"]["url_descarga"]
    filas = con.execute("select url, descargado, vigente from capturas "
                        "where fuente_id = 'ine_unidades_geoestadisticas_2023'").fetchall()
    # el zip del Censo viene del release crudos: no se registró cuándo se bajó del INE
    assert filas == [(url, None, True)]


# #54: la capa de CCZ del INE trae AREA_KM2 y AREA_HA intercambiados; la superficie se mide sobre la geometría
def test_superficie_de_los_ccz(con, salida):
    t = gpd.read_parquet(salida / "territorios.parquet").set_index("id")
    ccz = t[t.nivel == "ccz_mvd"]
    assert len(ccz) == 18
    for i, fila in ccz.iterrows():
        assert fila.area_km2 == pytest.approx(_area(fila.geometry), rel=0.01), i
    # los 18 CCZ cubren Montevideo: su superficie suma la del departamento (la del INE)
    assert ccz.area_km2.sum() == pytest.approx(t.loc["INE-2023/departamento/01"].area_km2, rel=0.02)



def test_superficie_coherente_con_la_geometria_en_todos_los_niveles(salida):
    """La superficie publicada de cada territorio está a ±1 % de su área medida (#54: así se detecta otro campo
    de superficie con unidades equivocadas)."""
    t = gpd.read_parquet(salida / "territorios.parquet")
    medida = t.to_crs(32721).area / 1e6
    fuera = ((t.area_km2 / medida) - 1).abs() > 0.01
    assert not fuera.any(), t.loc[fuera, ["id", "area_km2"]].assign(medida=medida[fuera]).head().to_string()
    assert set(t.nivel) >= {"departamento", "seccion", "segmento", "localidad", "barrio_mvd", "ccz_mvd",
                            "municipio_mvd", "pais"}
