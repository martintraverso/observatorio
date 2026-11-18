"""F2.4 (#43): parser del informe «Mercado de trabajo por área geográfica de residencia» (AC-L5…L10).

Golden tests sobre los tres fixtures de F2.1 (feb 2022, jul–set 2024, jul–set 2026). Los valores esperados se
copiaron a mano de las tablas del informe, no de la salida del parser.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest
from ech_mercado_trabajo import (
    INDICADORES,
    MUNICIPIOS,
    ErrorInforme,
    codigo_departamento,
    numero,
    parsear_informe,
    periodo_del_informe,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "ech_mt"


def html(nombre: str) -> str:
    return (FIX / nombre).read_text(encoding="utf-8")


def celda(texto: str) -> re.Pattern:
    """Una celda <td ...> cuyo contenido es `texto` (las celdas traen estilos y saltos de línea)."""
    return re.compile(r"(<t[dh][^>]*>\s*)" + re.escape(texto) + r"(\s*</t[dh]>)")


def cambiar_celda(h: str, viejo: str, nuevo: str, desde: str | None = None) -> str:
    """Cambia la primera celda `viejo` (después de la celda `desde`, si se da) por `nuevo`."""
    i = celda(desde).search(h).end() if desde else 0
    m = celda(viejo).search(h, i)
    assert m, viejo
    return h[:m.start()] + m.group(1) + nuevo + m.group(2) + h[m.end():]


def sin_fila(h: str, texto: str) -> str:
    m = celda(texto).search(h)
    assert m, texto
    return h[:h.rfind("<tr", 0, m.start())] + h[h.index("</tr>", m.end()) + len("</tr>"):]


@pytest.fixture(scope="module")
def informes() -> dict:
    return {f: parsear_informe(html(f"ech_mt_{f}.html")) for f in ["2022_02", "2024_09", "2026_09"]}


def valores(df, codigo, *indicadores):
    fila = df[df.codigo == codigo].set_index("indicador").valor
    return [fila[i] for i in indicadores]


TASAS = ("tasa_actividad", "tasa_empleo", "tasa_desempleo")
MILES = ("activos", "ocupados", "desocupados")


# AC-L5
@pytest.mark.parametrize("informe, con_total", [("2022_02", False), ("2024_09", False), ("2026_09", True)])
def test_extrae_los_siete_indicadores_por_territorio(informes, informe, con_total):
    df = informes[informe]
    assert set(df.indicador) == set(INDICADORES)
    deptos = df[df.nivel == "departamento"]
    assert sorted(deptos.codigo.unique()) == [f"{i:02d}" for i in range(1, 20)]
    assert sorted(df[df.nivel == "municipio_mvd"].codigo.unique()) == sorted(MUNICIPIOS)
    assert (df.nivel == "pais").any() == con_total  # solo si el informe publica «Total país»
    if con_total:
        assert set(df[df.nivel == "pais"].territorio_id) == {"INE-2023/pais/UY"}
    # una fila por territorio e indicador; «Total Montevideo» no se guarda de nuevo
    assert not df.duplicated(["territorio_id", "indicador"]).any()
    assert len(df) == (19 + 8 + con_total) * 7
    assert set(df.nivel) <= {"pais", "departamento", "municipio_mvd"}
    assert dict(zip(df.indicador, df.unidad)) == {
        "tasa_actividad": "%", "tasa_empleo": "%", "tasa_desempleo": "%", "tasa_no_registro": "%",
        "activos": "miles de personas", "ocupados": "miles de personas", "desocupados": "miles de personas"}
    assert not df.es_estimado.any()


# AC-L6
def test_nombres_de_departamento_a_codigos_ine():
    assert codigo_departamento("Montevideo") == "01"
    assert codigo_departamento("  TREINTA  y tres ") == "19"
    assert codigo_departamento("Paysandu") == "11"
    assert codigo_departamento("río negro") == "12"
    assert codigo_departamento("Tacuarembó") == "18"
    with pytest.raises(ErrorInforme, match="Departamento desconocido"):
        codigo_departamento("Atlántida")


def test_un_departamento_desconocido_frena_el_informe():
    with pytest.raises(ErrorInforme, match="Departamento desconocido"):
        parsear_informe(cambiar_celda(html("ech_mt_2024_09.html"), "Artigas", "Artiga"))


# AC-L7
def test_separadores_decimales():
    assert numero("7,1") == 7.1
    assert numero("14.2") == 14.2
    assert numero("1900,6") == 1900.6
    for malo in ["", "s/d", "7,1,2", "1.900,6"]:
        with pytest.raises(ErrorInforme):
            numero(malo)


def test_punto_decimal_en_cuadros_3_y_6_de_2022(informes):
    df = informes["2022_02"]
    assert valores(df, "01", "tasa_no_registro") == [14.2]
    assert valores(df, "A", "tasa_no_registro") == [23.5]


def test_ninguna_fila_se_descarta_en_silencio():
    original = html("ech_mt_2024_09.html")
    with pytest.raises(ErrorInforme, match="filas"):
        parsear_informe(sin_fila(original, "Artigas"))
    with pytest.raises(ErrorInforme, match="Número"):
        parsear_informe(cambiar_celda(original, "63,9", "s/d"))


# AC-L8
def test_valores_del_informe_jul_set_2026(informes):
    df = informes["2026_09"]
    assert valores(df, "UY", *TASAS) == [64.1, 59.5, 7.1]
    assert valores(df, "01", *TASAS) == [65.5, 60.8, 7.2]
    assert valores(df, "10", *TASAS) == [69.1, 65.3, 5.5]
    assert valores(df, "19", *TASAS) == [54.1, 48.6, 10.2]
    assert valores(df, "UY", *MILES, "tasa_no_registro") == [1900.6, 1765.9, 134.7, 21.0]
    assert valores(df, "A", *TASAS, *MILES, "tasa_no_registro") == [63.8, 58.1, 8.9, 103.3, 94.1, 9.2, 28.2]


# AC-L9
def test_valores_del_informe_feb_2022(informes):
    df = informes["2022_02"]
    assert valores(df, "01", *TASAS, *MILES) == [63.2, 58.7, 7.2, 724.7, 672.3, 52.4]
    assert valores(df, "02", *TASAS, *MILES, "tasa_no_registro") == [58.1, 53.6, 8.2, 34.3, 31.6, 2.8, 44.6]
    assert valores(df, "19", *TASAS) == [57.1, 53.3, 6.8]
    # cuadro 5 trae PET: no es un indicador del observatorio y no se guarda
    assert valores(df, "A", *MILES) == [103.4, 92.0, 11.4]
    assert valores(df, "G", *TASAS, "tasa_no_registro") == [57.3, 50.9, 11.1, 20.1]


def test_valores_del_informe_jul_set_2024(informes):
    df = informes["2024_09"]
    assert valores(df, "01", *TASAS, *MILES, "tasa_no_registro") == [65.3, 60.4, 7.6, 750.5, 693.4, 57.1, 13.8]
    assert valores(df, "02", *TASAS) == [63.9, 56.1, 12.2]
    assert valores(df, "B", *TASAS, *MILES, "tasa_no_registro") == [71.9, 67.4, 6.2, 97.5, 91.5, 6.0, 7.4]


def test_un_formato_desconocido_frena_el_informe():
    with pytest.raises(ErrorInforme, match="Encabezado desconocido"):
        parsear_informe(cambiar_celda(html("ech_mt_2024_09.html"), "Tasa de Actividad", "Tasa de Participación"))
    with pytest.raises(ErrorInforme, match="cuadros"):
        sin_un_cuadro = html("ech_mt_2026_09.html")
        i = sin_un_cuadro.rindex("<table")
        parsear_informe(sin_un_cuadro[:i] + sin_un_cuadro[sin_un_cuadro.index("</table>", i) + 8:])


def test_total_montevideo_tiene_que_repetir_el_departamento():
    with pytest.raises(ErrorInforme, match="Total Montevideo"):
        parsear_informe(cambiar_celda(html("ech_mt_2026_09.html"), "65,5", "65,4", desde="Total Montevideo"))


# AC-L10
@pytest.mark.parametrize("informe, inicio, fin, etiqueta", [
    ("2022_02", "2021-12-01", "2022-02-28", "2021-12/2022-02"),
    ("2024_09", "2024-07-01", "2024-09-30", "2024-07/2024-09"),
    ("2026_09", "2026-07-01", "2026-09-30", "2026-07/2026-09"),
])
def test_periodo_trimestre_movil(informes, informe, inicio, fin, etiqueta):
    df = informes[informe]
    assert set(df.tipo_periodo) == {"trimestre_movil"}
    assert set(df.periodo) == {etiqueta}
    assert set(df.periodo_inicio) == {dt.date.fromisoformat(inicio)}
    assert set(df.periodo_fin) == {dt.date.fromisoformat(fin)}


def test_periodo_desde_el_nombre_del_archivo_y_coherencia():
    sin_titulo = "<html><body><p>Sin encabezado</p></body></html>"
    assert periodo_del_informe(sin_titulo, "Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.html").etiqueta == "2026-07/2026-09"
    assert periodo_del_informe(sin_titulo, "Informe_departamental-Julio-Setiembre2024.html").etiqueta == "2024-07/2024-09"
    assert periodo_del_informe(sin_titulo, "Mercado Laboral por Área Geográfica de Residencia - feb 2022.html").etiqueta \
        == "2021-12/2022-02"
    with pytest.raises(ErrorInforme, match="período"):
        periodo_del_informe(sin_titulo, "informe.html")
    with pytest.raises(ErrorInforme, match="no coincide"):
        periodo_del_informe(html("ech_mt_2026_09.html"), "Mercado_trabajo_IN_SOC_MTR_2026_M_08-_v1_0.html")


def test_los_cuadros_de_un_nivel_coinciden_en_la_fila_de_total():
    with pytest.raises(ErrorInforme, match="fila de total"):
        parsear_informe(sin_fila(html("ech_mt_2026_09.html"), "Total país"))


@pytest.mark.parametrize("texto, fin", [
    ("Actividad, Empleo y Desempleo Febrero 2022 Introducción", (2022, 2)),
    ("Actividad, Empleo y Desempleo Trimestre móvil: Noviembre 2023 - Enero 2024 Introducción", (2024, 1)),
    ("Actividad, Empleo y Desempleo Trimestre móvil: Diciembre 2024 - Febrero 2025 Introducción", (2025, 2)),
    ("Actividad, Empleo y Desempleo Trimestre móvil: Noviembre - Enero 2024 Introducción", (2024, 1)),
])
def test_periodos_que_cruzan_el_año(texto, fin):
    h = f"<html><body><p>{texto}</p></body></html>"
    p = periodo_del_informe(h)
    assert (p.fin.year, p.fin.month) == fin


@pytest.mark.parametrize("archivo, etiqueta", [
    ("Informe_departamental-Diciembre2024-Febrero.html", "2024-12/2025-02"),
    ("mercado-trabajo-area-geografica-residencia-ech-noviembre-2023-enero-2024", "2023-11/2024-01"),
    ("Mercado de trabajo por área geográfica de residencia - jul set 2022.html", "2022-07/2022-09"),
    ("Informe_departamental-JUNIO-2022.knit.html", "2022-04/2022-06"),
])
def test_periodo_desde_nombres_reales_de_archivo(archivo, etiqueta):
    assert periodo_del_informe("<html></html>", archivo).etiqueta == etiqueta


@pytest.mark.parametrize("texto", [
    "Actividad, Empleo y Desempleo Trimestre móvil: Agosto - Setiembre 2024 Introducción",
    "Actividad, Empleo y Desempleo Trimestre móvil: Julio 2023 - Setiembre 2024 Introducción",
    "Actividad, Empleo y Desempleo Diciembre 2022 Febrero Marzo 2023 Introducción",
])
def test_un_periodo_desconocido_frena_el_informe(texto):
    with pytest.raises(ErrorInforme, match="Período desconocido"):
        periodo_del_informe(f"<html><body><p>{texto}</p></body></html>")


def test_el_encabezado_se_lee_aunque_haya_scripts_y_estilos_grandes():
    # Dentro del encabezado (entre el título e «Introducción»): si no se ignoraran, el período sería desconocido.
    relleno = ("<script>" + "x" * 500_000 + " Enero 1999 <table><tr><td>a</td></tr></table></script>"
               "<style>" + "y" * 100_000 + " Marzo 2001 </style>")
    h = html("ech_mt_2026_09.html")
    i = h.index("Trimestre móvil")
    i = h.rfind("<", 0, i)
    assert parsear_informe(h[:i] + relleno + h[i:]).periodo.iloc[0] == "2026-07/2026-09"


def test_codigo_de_documento_con_mes_invalido():
    with pytest.raises(ErrorInforme, match="Período desconocido"):
        periodo_del_informe("<html></html>", "Mercado_trabajo_IN_SOC_MTR_2026_M_13-_v1_0.html")
