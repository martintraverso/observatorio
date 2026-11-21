"""F3.3 (#127): parser de las series de ingresos del INE (AC-I7…AC-I11), sobre los fixtures de F3.1.

`parsear_serie(xlsx_bytes, codigo)` es pura: sin red ni disco. Decisiones del mantenedor (PR #134, 2026-11-20):
las unidades son «por mes», los totales anuales se guardan aunque sean el promedio de la planilla y los valores
de 2026 se guardan redondeados como vienen.
"""

from __future__ import annotations

import datetime as dt
import io
import re
import zipfile
from pathlib import Path

import pytest
import yaml
from ech_ingresos import INDICADORES, ErrorSerie, parsear_serie

from comun.periodos import anio, trimestre
from comun.xlsx import leer_primera_hoja

FIX = Path(__file__).resolve().parent / "fixtures" / "ech_ingresos"
REGISTRO = Path(__file__).resolve().parents[1] / "fuentes" / "ine_ech_ingresos_series.yml"
PAIS, MVD = "INE-2023/pais/UY", "INE-2023/departamento/01"
INTERIOR, I5000, MENORES = (f"INE-2023/region/{c}" for c in ("interior", "interior-5000", "interior-menores"))


def leer(codigo: str) -> bytes:
    return (FIX / f"{codigo}.xlsx").read_bytes()


@pytest.fixture(scope="module")
def ing07():
    return parsear_serie(leer("ECHING07"), "ECHING07")


def valor(df, territorio, periodo):
    v = df[(df.territorio_id == territorio) & (df.periodo == periodo)].valor
    assert len(v) == 1, (territorio, periodo, len(v))
    return float(v.iloc[0])


# ------------------------------------------------------------------ AC-I7

def test_columnas_a_territorios(ing07):
    assert set(ing07.territorio_id) == {PAIS, MVD, INTERIOR, I5000, MENORES}
    # cada período tiene exactamente un valor por territorio
    assert (ing07.groupby(["periodo", "territorio_id"]).size() == 1).all()


def test_encabezado_con_y_sin_tilde():
    """ECHING07 dice «Total Pais»; ECHINGRESOS2, «Total País»: los dos son el país."""
    df = parsear_serie(leer("ECHINGRESOS2"), "ECHINGRESOS2")
    assert PAIS in set(df.territorio_id)


def _cambiar_texto(xlsx: bytes, viejo: str, nuevo: str) -> bytes:
    """Copia del xlsx con un texto compartido cambiado (para simular un formato nuevo del INE)."""
    entrada, salida = zipfile.ZipFile(io.BytesIO(xlsx)), io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for info in entrada.infolist():
            datos = entrada.read(info.filename)
            if info.filename == "xl/sharedStrings.xml":
                assert f">{viejo}<".encode() in datos, viejo
                datos = datos.replace(f">{viejo}<".encode(), f">{nuevo}<".encode(), 1)
            z.writestr(info, datos)
    return salida.getvalue()


def test_columna_desconocida_falla():
    with pytest.raises(ErrorSerie, match="(?i)columna"):
        parsear_serie(_cambiar_texto(leer("ECHING07"), "Montevideo", "Montevideo y Canelones"), "ECHING07")


def test_planilla_que_no_es_la_esperada_falla():
    """El título tiene que corresponder al código (variante y base de precios): si el INE cambia un archivo de
    lugar, no se carga con otro indicador."""
    with pytest.raises(ErrorSerie, match="(?i)título"):
        parsear_serie(leer("ECHING09"), "ECHING07")
    with pytest.raises(ErrorSerie, match="(?i)código"):
        parsear_serie(leer("ECHING07"), "ECHING99")


# ------------------------------------------------------------------ AC-I8

def test_filas_a_periodos(ing07):
    t1 = ing07[ing07.periodo == "2016-T1"].iloc[0]
    assert (t1.tipo_periodo, t1.periodo_inicio, t1.periodo_fin) == ("trimestre", dt.date(2016, 1, 1), dt.date(2016, 3, 31))
    t3 = ing07[ing07.periodo == "2016-T3"].iloc[0]
    assert (t3.periodo_inicio, t3.periodo_fin) == (dt.date(2016, 7, 1), dt.date(2016, 9, 30))
    a = ing07[ing07.periodo == "2016"].iloc[0]
    assert (a.tipo_periodo, a.periodo_inicio, a.periodo_fin) == ("anio", dt.date(2016, 1, 1), dt.date(2016, 12, 31))
    assert trimestre(2016, 4).columnas()["periodo_fin"] == dt.date(2016, 12, 31)
    assert anio(2016).etiqueta == "2016"


def test_cantidad_de_periodos(ing07):
    """2016–2025: 4 trimestres y el total de cada año; 2026: los tres trimestres publicados. Las filas de año
    y las notas al pie no son datos."""
    periodos = ing07.drop_duplicates("periodo")
    assert (periodos.tipo_periodo == "trimestre").sum() == 43
    assert (periodos.tipo_periodo == "anio").sum() == 10
    assert sorted(periodos[periodos.tipo_periodo == "anio"].periodo) == [str(a) for a in range(2016, 2026)]
    assert {"2026-T1", "2026-T2", "2026-T3"} <= set(periodos.periodo) and "2026" not in set(periodos.periodo)
    assert len(ing07) == 53 * 5


def test_llamadas_fuera_de_la_etiqueta_y_su_texto_guardado(ing07):
    assert not any(re.search(r"\(\d\)", p) for p in ing07.periodo)
    assert ing07.attrs["llamadas"] == {"2026-T1": ["Cifras actualizadas a noviembre 2026."],
                                       "2026-T2": ["Cifras actualizadas a noviembre 2026."]}
    assert "Las cifras presentadas están sujetas a revisión, en función del cierre anual de la base." in ing07.attrs["notas_al_pie"]


# ------------------------------------------------------------------ AC-I9

def test_indicador_y_unidad_por_planilla(ing07):
    assert set(ing07.indicador) == {"ing_hogar_medio_cagu_cvl"} and set(ing07.unidad) == {"pesos corrientes por mes"}
    df = parsear_serie(leer("ECHINGRESOS2"), "ECHINGRESOS2")
    assert set(df.indicador) == {"ing_hogar_medio_sagu_svl_ene2005"}
    assert set(df.unidad) == {"pesos de enero de 2005 por mes"}


def test_indicadores_coinciden_con_el_registro():
    archivos = {a["codigo"]: a["indicador"] for a in yaml.safe_load(REGISTRO.read_text(encoding="utf-8"))["archivos"]}
    assert {c: i["indicador"] for c, i in INDICADORES.items()} == {c: i for c, i in archivos.items() if i}
    assert len({i["indicador"] for i in INDICADORES.values()}) == 10  # distintos por medida, variante y base


# ------------------------------------------------------------------ AC-I10

def test_precision_completa(ing07):
    assert valor(ing07, PAIS, "2016-T1") == 59534.00275705033
    assert valor(ing07, PAIS, "2026-T1") == 124365  # 2026 viene redondeado en la planilla: se guarda tal cual
    assert not ing07.es_estimado.any()


# ------------------------------------------------------------------ AC-I11 (dorados)

@pytest.mark.parametrize("periodo,pais,mvd", [("2016", 58072, 69557), ("2023", 96230, 118532), ("2025", 110097, 133145)])
def test_dorados_ech_ing07(ing07, periodo, pais, mvd):
    assert (round(valor(ing07, PAIS, periodo)), round(valor(ing07, MVD, periodo))) == (pais, mvd)


def test_dorados_ech_ing09_y_primer_trimestre(ing07):
    df = parsear_serie(leer("ECHING09"), "ECHING09")
    assert (round(valor(df, PAIS, "2016")), round(valor(df, MVD, "2016"))) == (49809, 59404)
    assert ing07.periodo_inicio.min() == dt.date(2016, 1, 1)
    assert round(valor(ing07, PAIS, "2016-T1")) == 59534


# ------------------------------------------------------------------ F3.4d (#140): cada formato inesperado falla

def _cambiar_hoja(xlsx: bytes, viejo: bytes, nuevo: bytes) -> bytes:
    """Copia del xlsx con un cambio en el XML de la hoja."""
    entrada, salida = zipfile.ZipFile(io.BytesIO(xlsx)), io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for info in entrada.infolist():
            datos = entrada.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                assert viejo in datos, viejo
                datos = datos.replace(viejo, nuevo, 1)
            z.writestr(info, datos)
    return salida.getvalue()


@pytest.mark.parametrize("viejo,nuevo,error", [
    ("Total 2016", "Promedio 2016", "fila .* desconocida"),                 # fila desconocida
    ("Total 2017", "Total 2016", "aparece dos veces|año"),                  # período repetido (o de otro bloque)
    ("Abril - Junio/16", "Abril - Junio/16 (7)", r"llamada \(7\)"),         # llamada sin nota al pie
    ("Interior", "Otras áreas", "(?i)columna"),                             # «Total» sin «Interior»
    ("Enero - Marzo/17", "Enero - Marzo/16", "aparece dos veces|año"),      # año del trimestre ≠ bloque
])
def test_textos_inesperados_fallan(viejo, nuevo, error):
    with pytest.raises(ErrorSerie, match=error):
        parsear_serie(_cambiar_texto(leer("ECHING07"), viejo, nuevo), "ECHING07")


def test_trimestre_con_el_anio_de_otro_bloque_falla():
    """«Julio - Setiembre/61» dentro del bloque 2016 no se carga como 2061."""
    with pytest.raises(ErrorSerie, match="año"):
        parsear_serie(_cambiar_texto(leer("ECHING07"), "Julio - Setiembre/16", "Julio - Setiembre/61"), "ECHING07")


def test_columna_faltante_falla():
    """Sin la columna Montevideo (la celda del encabezado vacía), falta un territorio."""
    xlsx = _cambiar_texto(leer("ECHING07"), "Montevideo", "")
    with pytest.raises(ErrorSerie, match="(?i)falta|columna"):
        parsear_serie(xlsx, "ECHING07")


def test_numeros_en_el_pie_fallan():
    """Una fila con números después de «Fuente:» no se toma como nota al pie."""
    c = leer_primera_hoja(leer("ECHING07"))
    fila_fuente = next(r for r, x in c.items() if str(x.get(1, "")).startswith("Fuente:"))
    xlsx = _cambiar_hoja(leer("ECHING07"), f'<row r="{fila_fuente + 1}"'.encode(),
                         f'<row r="{fila_fuente + 1}"><c r="B{fila_fuente + 1}"><v>123</v></c></row><row r="999"'.encode())
    with pytest.raises(ErrorSerie, match="pie"):
        parsear_serie(xlsx, "ECHING07")


def test_llamada_2_de_las_planillas_per_capita():
    """En las per cápita «(1)» es del título y «(2)» marca las cifras actualizadas: la numeración se respeta."""
    xlsx = _cambiar_texto(leer("ECHING07"), "(1): Cifras actualizadas a noviembre 2026.", "(2): Cifras actualizadas a noviembre 2026.")
    for t in ("Enero - Marzo/26 (1)", "Abril - Junio/26 (1)"):
        xlsx = _cambiar_texto(xlsx, t, t.replace("(1)", "(2)"))
    df = parsear_serie(xlsx, "ECHING07")
    assert df.attrs["llamadas"]["2026-T1"] == ["Cifras actualizadas a noviembre 2026."]


def test_lector_busca_la_primera_hoja_en_el_libro():
    """La primera hoja es la que dice workbook.xml, aunque su archivo no se llame sheet1.xml."""
    entrada, salida = zipfile.ZipFile(io.BytesIO(leer("ECHING07"))), io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for info in entrada.infolist():
            datos = entrada.read(info.filename)
            nombre = info.filename.replace("sheet1.xml", "hoja_ingresos.xml")
            if info.filename in ("xl/_rels/workbook.xml.rels", "[Content_Types].xml"):
                datos = datos.replace(b"sheet1.xml", b"hoja_ingresos.xml")
            z.writestr(nombre, datos)
    assert len(parsear_serie(salida.getvalue(), "ECHING07")) == 53 * 5


def test_celda_sin_referencia_falla():
    xlsx = _cambiar_hoja(leer("ECHING07"), b'<c r="B11"', b'<c')
    with pytest.raises(ErrorSerie, match="referencia"):
        parsear_serie(xlsx, "ECHING07")
