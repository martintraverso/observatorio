"""F4.3a (#179): parser del anuario del MEC (AC-E8–E12, E14, E15; AC-E13 con D7)."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import mec_anuario as mec
import pytest
import yaml

from comun.xlsx import _hojas

RAIZ = Path(__file__).resolve().parents[1]
REG = yaml.safe_load((RAIZ / "fuentes" / "mec_anuario_educacion.yml").read_text(encoding="utf-8"))
FIX = RAIZ / "tests" / "fixtures" / "mec_anuario"
XLSX = {a: (FIX / f"{a}.xlsx").read_bytes() for a in (2024, 2023)}


def cuadro(cod, anio=2024, xlsx=None, mapeo=None):
    e = REG["cuadros"][cod]
    return mec.parsear_cuadro(xlsx or XLSX[anio], cod, anio, mapeo if mapeo is not None else e["mapeo"][anio],
                              e["tipos"][anio])


def valor(c, indicador, territorio):
    d = c.datos
    fila = d[(d.indicador == indicador) & (d.territorio_id == mec.tid(*territorio.split("/")))]
    assert len(fila) == 1, (indicador, territorio)
    return fila.valor.iloc[0]


def cambiar(xlsx: bytes, archivo_de, cambio) -> bytes:
    """Copia del xlsx con un archivo interno cambiado (`archivo_de(zip)` dice cuál; `cambio(texto)` lo cambia)."""
    entrada = zipfile.ZipFile(io.BytesIO(xlsx))
    destino = archivo_de(entrada)
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for i in entrada.infolist():
            datos = entrada.read(i.filename)
            if i.filename == destino:
                datos = cambio(datos.decode("utf-8")).encode("utf-8")
            z.writestr(i, datos)
    return salida.getvalue()


def hoja_xml(cod):
    return lambda z: next(ruta for nombre, ruta in _hojas(z).items() if nombre.strip() == cod)


def celda_texto(ref, texto):
    """Reemplaza el valor de la celda `ref` por un texto en línea."""
    def f(xml):
        nuevo, n = re.subn(rf'<c r="{ref}"[^>]*?(/>|>.*?</c>)', f'<c r="{ref}" t="inlineStr"><is><t>{texto}</t></is></c>', xml, count=1)
        assert n == 1, ref
        return nuevo
    return f


# ---------------------------------------------------------------- todos los cuadros de la ola 1

@pytest.mark.parametrize("anio", [2024, 2023])
def test_cada_cuadro_de_la_ola_1_se_lee_con_su_mapeo(anio):
    """Las rutas del archivo coinciden con las del registro columna por columna (AC-E9) y cada fila de un cuadro
    tipo A es un territorio conocido (AC-E8)."""
    leidos = 0
    for cod, e in REG["cuadros"].items():
        if e["ola"] != 1 or anio not in e["anios"] or e["mapeo"].get(anio) is None:
            continue
        c = cuadro(cod, anio)
        todo_omitido = all(m.get("omitir") for m in e["mapeo"][anio])  # II-2.3.2 2024: datos de 2022, ya cargados (D4)
        assert len(c.datos) or todo_omitido or any("total en 0" in a for a in c.avisos), cod  # II-2.2.18 2023: todo «s/d»
        assert c.datos.valor.map(lambda v: isinstance(v, int)).all(), cod
        leidos += 1
    assert leidos >= 50


# ---------------------------------------------------------------- AC-E15: valores de control

def test_ac_e15_ii_2_2_1_2024():
    c = cuadro("II-2.2.1")
    pre = "edu_ii_2_2_1_forma_de_administracion_"
    assert valor(c, "edu_ii_2_2_1_total", "pais/UY") == 284944
    assert valor(c, pre + "publica_total", "pais/UY") == 237385
    assert valor(c, pre + "privada_total", "pais/UY") == 47559
    assert valor(c, pre + "publica_sexo_v", "pais/UY") == 122200
    assert valor(c, pre + "publica_sexo_m", "pais/UY") == 115185
    assert valor(c, "edu_ii_2_2_1_total", "departamento/01") == 102182
    assert valor(c, "edu_ii_2_2_1_total", "region/interior") == 182762
    assert valor(c, "edu_ii_2_2_1_total", "departamento/02") == 7209  # Artigas
    assert valor(c, "edu_ii_2_2_1_total", "departamento/03") == 48638  # Canelones


def test_ac_e15_ii_2_2_1_2023():
    c = cuadro("II-2.2.1", 2023)
    pre = "edu_ii_2_2_1_forma_de_administracion_total_"
    assert valor(c, "edu_ii_2_2_1_total", "pais/UY") == 287805
    assert valor(c, pre + "varon", "pais/UY") == 147955
    assert valor(c, pre + "mujer", "pais/UY") == 139655


def test_ac_e15_ii_2_2_13_2024():
    c = cuadro("II-2.2.13")
    pre = "edu_ii_2_2_13_rendimiento_escolar_"
    assert valor(c, pre + "promovidos_total", "pais/UY") == 232567
    assert valor(c, pre + "no_promovidos_total", "pais/UY") == 4818
    assert valor(c, pre + "promovidos_total", "departamento/01") == 71109
    assert valor(c, pre + "no_promovidos_total", "departamento/01") == 2616


def test_ac_e15_y_e14_serie_nacional_2024():
    s = mec.parsear_serie_matricula(XLSX[2024])
    s24 = s[s.periodo == "2024"].set_index("ruta").valor
    assert s24["TOTAL SISTEMA"] == 1042564
    assert s24["Total Educación Primaria/Primaria Común"] == 284944
    # AC-E14: país, un valor por año, nivel y forma de administración
    assert set(s.territorio_id) == {mec.PAIS}
    assert not s.duplicated(["indicador", "periodo"]).any()
    assert {"2002", "2024"} <= set(s.periodo) and set(s.tipo_periodo) == {"anio"}
    assert s24["Total Educación Primaria/Primaria Común/Común pública"] == 237385
    assert "Total Educación Media/Total Educación Media Básica/Total Media Básica General/Pública" in s24.index


# ---------------------------------------------------------------- AC-E8: territorios

def test_ac_e8_filas_a_territorios():
    c = cuadro("II-2.2.1")
    t = set(c.datos.territorio_id)
    assert len(t) == 21  # país, Montevideo, Resto del país y 18 departamentos
    assert {mec.PAIS, mec.INTERIOR, mec.tid("departamento", "01"), mec.tid("departamento", "19")} <= t
    assert mec.territorio_de_fila("  RÍO   negro ") == mec.tid("departamento", "12")
    assert mec.territorio_de_fila("TOTAL DEL PAÍS") == mec.PAIS


def test_ac_e8_una_fila_desconocida_hace_fallar():
    x = cambiar(XLSX[2024], hoja_xml("II-2.2.1"), celda_texto("A12", "Artigaz"))
    with pytest.raises(mec.ErrorAnuario, match="Artigaz"):
        cuadro("II-2.2.1", xlsx=x)


# ---------------------------------------------------------------- AC-E9: encabezados y mapeo

def test_ac_e9_una_columna_que_no_esta_en_el_mapeo_hace_fallar():
    mapeo = [m for m in REG["cuadros"]["II-2.2.1"]["mapeo"][2024] if m["col"] != "H"]
    with pytest.raises(mec.ErrorAnuario, match="no está en el mapeo"):
        cuadro("II-2.2.1", mapeo=mapeo)


def test_ac_e9_una_ruta_distinta_hace_fallar():
    mapeo = [dict(m) for m in REG["cuadros"]["II-2.2.1"]["mapeo"][2024]]
    mapeo[1]["ruta"] = "OTRA COSA"
    with pytest.raises(mec.ErrorAnuario, match="OTRA COSA"):
        cuadro("II-2.2.1", mapeo=mapeo)


def test_ac_e9_una_columna_mapeada_que_falta_en_el_archivo_hace_fallar():
    mapeo = [*REG["cuadros"]["II-2.2.1"]["mapeo"][2024], {"col": "Z", "ruta": "X", "id": "edu_x"}]
    with pytest.raises(mec.ErrorAnuario, match="no tiene"):
        cuadro("II-2.2.1", mapeo=mapeo)


# ---------------------------------------------------------------- AC-E10: año

def test_ac_e10_periodo_anual_del_titulo():
    d = cuadro("II-2.2.1").datos
    assert set(d.periodo) == {"2024"} and set(d.tipo_periodo) == {"anio"}
    assert str(d.periodo_inicio.iloc[0]) == "2024-01-01" and str(d.periodo_fin.iloc[0]) == "2024-12-31"


def test_ac_e10_un_titulo_de_otro_anio_hace_fallar():
    e = REG["cuadros"]["II-2.2.1"]
    with pytest.raises(mec.ErrorAnuario, match="AC-E10"):
        mec.parsear_cuadro(XLSX[2024], "II-2.2.1", 2023, e["mapeo"][2024], "A")


def test_d4_una_columna_de_otro_anio_va_con_su_anio_real():
    mapeo = [dict(m) for m in REG["cuadros"]["II-2.2.1"]["mapeo"][2024]]
    for m in mapeo:
        if "privada" in m["id"]:
            m["anio"] = 2022
    d = cuadro("II-2.2.1", mapeo=mapeo).datos
    assert set(d[d.indicador.str.contains("privada")].periodo) == {"2022"}
    assert set(d[~d.indicador.str.contains("privada")].periodo) == {"2024"}


# ---------------------------------------------------------------- AC-E11: valores

def test_ac_e11_lo_que_no_es_dato_no_crea_fila_y_se_cuenta():
    x = cambiar(XLSX[2024], hoja_xml("II-2.2.1"), celda_texto("B12", "-"))
    c = cuadro("II-2.2.1", xlsx=x)
    assert c.sin_dato == cuadro("II-2.2.1").sin_dato + 1
    d = c.datos
    assert d[(d.indicador == "edu_ii_2_2_1_total") & (d.territorio_id == mec.tid("departamento", "02"))].empty


def test_ac_e11_un_texto_que_no_es_numero_ni_falta_de_dato_hace_fallar():
    x = cambiar(XLSX[2024], hoja_xml("II-2.2.1"), celda_texto("B12", "siete mil"))
    with pytest.raises(mec.ErrorAnuario, match="siete mil"):
        cuadro("II-2.2.1", xlsx=x)


def test_ac_e11_numeros_guardados_como_texto_se_leen_como_enteros():
    mapeo = [{k: v for k, v in m.items() if k != "omitir"} for m in REG["cuadros"]["II-2.3.2"]["mapeo"][2024]]
    c = cuadro("II-2.3.2", mapeo=mapeo)  # II-2.3.2 guarda «7466» como texto (en el registro va omitido: es de 2022)
    assert len(c.datos) > 0
    assert c.datos.valor.map(lambda v: isinstance(v, int)).all()
    assert c.avisos and "título no dice el año" in c.avisos[0]


# ---------------------------------------------------------------- AC-E12: pie

def test_ac_e12_fuente_y_notas_van_al_pie_y_no_a_los_datos():
    c = cuadro("II-2.2.1")
    assert c.codigo == "II-2.2.1"
    assert any(p.startswith("Fuente:") for p in c.pie)
    assert "Nota: Pública no incluye JICI." in c.pie
    assert not c.datos.celda.str.match(r"^[A-Z]+3[0-9]$").any()  # filas 30–32: pie


def test_ac_e12_notas_que_siguen_sin_rotulo_tambien_van_al_pie():
    c = cuadro("II-3.1.2")
    assert any(p.startswith("2- Dentro de la cantidad de establecimientos") for p in c.pie)


# ---------------------------------------------------------------- AC-E13 y D7

def test_ac_e13_el_sexo_de_2023_y_2024_no_comparten_indicador():
    pre = "edu_ii_2_2_1_forma_de_administracion_total_"
    d23, d24 = cuadro("II-2.2.1", 2023).datos, cuadro("II-2.2.1").datos
    assert {pre + "varon", pre + "mujer"} <= set(d23.indicador)
    assert not set(d24.indicador) & {pre + "varon", pre + "mujer"}  # 2024: solo pública, no se carga (D7)


# ---------------------------------------------------------------- tipo B

def test_tipo_b_con_la_categoria_en_el_indicador_y_los_totales_que_nombran_territorio():
    """II-3.2.1: «TOTAL DEL PAÍS», «TOTAL MONTEVIDEO» y «TOTAL RESTO DEL PAÍS» agrupan las mismas categorías; cada
    grupo va a su territorio (mantenedor, #180) con los mismos indicadores."""
    d = cuadro("II-3.2.1").datos
    assert set(d.territorio_id) == {mec.PAIS, mec.tid("departamento", "01"), mec.INTERIOR}
    por_t = d.groupby("territorio_id").indicador.agg(set)
    assert por_t[mec.PAIS] == por_t[mec.tid("departamento", "01")] == por_t[mec.INTERIOR]
    assert any(i.endswith("__diurna") for i in d.indicador) and any(i.endswith("__total") for i in d.indicador)
    assert not d.duplicated(["indicador", "territorio_id", "periodo"]).any()
    total = d[d.indicador.str.endswith("__total")].set_index("territorio_id").groupby(level=0).valor.first()
    assert total[mec.PAIS] == total[mec.tid("departamento", "01")] + total[mec.INTERIOR]  # 129.652 = 47.781 + 81.871


# ---------------------------------------------------------------- filas sin datos (revisión del PR #181)

def test_una_fila_de_territorio_con_todo_s_d_se_cuenta_y_no_se_ignora():
    c = cuadro("II-2.2.18", 2023)  # Montevideo, Resto del país y los 19 departamentos: todo «s/d»
    n = len(REG["cuadros"]["II-2.2.18"]["mapeo"][2023])
    assert c.sin_dato >= 20 * n


def test_un_total_en_0_sin_ningun_territorio_con_dato_no_se_carga():
    c = cuadro("II-2.2.18", 2023)  # el TOTAL suma celdas «s/d»: 0 en todas las columnas
    assert c.datos.empty
    assert any("total en 0" in a for a in c.avisos)


def todas_las_columnas(xlsx, cod, fila, texto, rotulo=None):
    cols = [m["col"] for m in REG["cuadros"][cod]["mapeo"][2024]]
    for col in cols:
        xlsx = cambiar(xlsx, hoja_xml(cod), celda_texto(f"{col}{fila}", texto))
    if rotulo:
        xlsx = cambiar(xlsx, hoja_xml(cod), celda_texto(f"A{fila}", rotulo))
    return xlsx, len(cols)


def test_un_departamento_con_todo_guiones_se_cuenta():
    x, n = todas_las_columnas(XLSX[2024], "II-2.2.1", 12, "-")  # Artigas
    c = cuadro("II-2.2.1", xlsx=x)
    assert c.sin_dato == cuadro("II-2.2.1").sin_dato + n - 2  # menos las 2 columnas con omitir (D7)
    assert mec.tid("departamento", "02") not in set(c.datos.territorio_id)


@pytest.mark.parametrize("texto", ["s/d", "siete mil"])
def test_una_fila_desconocida_sin_numeros_igual_hace_fallar(texto):
    x, _ = todas_las_columnas(XLSX[2024], "II-2.2.1", 12, texto, rotulo="Artigaz")
    with pytest.raises(mec.ErrorAnuario):
        cuadro("II-2.2.1", xlsx=x)


def test_tipo_b_el_total_general_no_abre_grupo():
    d = cuadro("II-3.2.7").datos
    categorias = {i.split("__")[-1] for i in d.indicador}
    assert not any(c.startswith("total_") and "anos" in c for c in categorias), sorted(categorias)[:5]


def test_serie_cuenta_lo_que_no_es_dato():
    assert mec.parsear_serie_matricula(XLSX[2024]).attrs["sin_dato"] > 0  # «S/D» y «n/c»


def test_ac_e8_rotulos_con_llamada_de_nota():
    assert mec.territorio_de_fila("Colonia*") == mec.tid("departamento", "05")
    assert mec.territorio_de_fila("Salto (1)") == mec.tid("departamento", "15")
    assert mec.territorio_de_fila("Total 2023") is None


def test_224_despues_del_pie_ninguna_fila_es_un_dato():
    """#224 (II-2.2.6 y II-2.2.8 de 2020): después de «Fuente:», una fila con números está fuera del cuadro (se cuenta y
    no se lee) y una de texto, en cualquier columna, sigue el pie."""
    celdas = {
        (3, 1): "Cuadro Nº II-2.2.6",
        (5, 1): "ESTUDIANTES MATRICULADOS EN EDUCACIÓN PRIMARIA PRIVADA SEGÚN DEPARTAMENTO (Todo el país, 2020)",
        (6, 1): "DEPARTAMENTO", (6, 2): "TOTAL",
        (8, 1): "TOTAL DEL PAÍS", (8, 2): 50762,
        (9, 1): "MONTEVIDEO", (9, 2): 30979,
        (10, 1): "Fuente: Procesamiento propio — DGEIP",
        (11, 2): "Primaria Privada: se carece de datos desagregados",  # la nota sigue en la columna B
        (40, 1): "30025", (40, 2): 2163,  # restos fuera del cuadro
    }
    e = mec.estructura(celdas, [], "II-2.2.6")
    assert [r for r, _ in e.filas] == [8, 9]
    assert e.fuera == 1
    assert any("se carece de datos desagregados" in p for p in e.pie)


def test_224_dos_filas_casi_iguales_son_dos_categorias():
    """#224 (mantenedor): II-1.3.5 de 2024 publica «…por el mec» y «…por el MEC» con valores distintos: son dos
    categorías, nada se suma, y el aviso lo dice. El registro dice cuál lleva __2 («…por el mec»): «…por el MEC»,
    la única fila de 2020–2023, conserva su id y su serie (AC-E13), sin depender del orden de las filas."""
    x = (FIX / "2024.xlsx").read_bytes()
    reg = yaml.safe_load((RAIZ / "fuentes" / "mec_anuario_educacion.yml").read_text(encoding="utf-8"))
    e = reg["cuadros"]["II-1.3.5"]
    assert e["categorias_segundas"][2024] == ["Otros cursos no reconocidos por el mec"]
    c = mec.parsear_cuadro(x, "II-1.3.5", 2024, e["mapeo"][2024], e["tipos"][2024], e["categorias_segundas"][2024])
    base = "edu_ii_1_3_5_funcion_total__otros_cursos_no_reconocidos_por_el_mec"
    total = c.datos[c.datos.indicador.isin([base, base + "__2"])].set_index("indicador").valor
    assert total.to_dict() == {base: 206, base + "__2": 15}
    assert c.categorias[base] == "Otros cursos no reconocidos por el MEC"
    assert any("casi igual" in a for a in c.avisos)
    # sin la regla del registro, por el orden de las filas el id de la serie quedaría con la otra categoría
    sin_regla = mec.parsear_cuadro(x, "II-1.3.5", 2024, e["mapeo"][2024], e["tipos"][2024])
    assert sin_regla.datos[sin_regla.datos.indicador == base].valor.iloc[0] == 15


def test_224_d4_en_la_ola_2():
    """#224: D4 vale en la ola 2. II-1.3.2 de 2023 y 2024 repite 2022 («último año disponible»): no se vuelve a
    cargar. II-2.2.12: lo privado de 2022 es copia de 2021 (datos de 2020) y no se carga; 2023 difiere y queda."""
    reg = yaml.safe_load((RAIZ / "fuentes" / "mec_anuario_educacion.yml").read_text(encoding="utf-8"))["cuadros"]
    for anio in (2023, 2024):
        assert all(x.get("omitir") for x in reg["II-1.3.2"]["mapeo"][anio])
    privadas = lambda a: [x for x in reg["II-2.2.12"]["mapeo"][a] if "privad" in x["id"]]  # noqa: E731
    assert all(x.get("anio") == 2020 for x in privadas(2021))
    assert all(x.get("omitir") for x in privadas(2022))
    assert not any(x.get("omitir") or x.get("anio") for x in privadas(2023))
