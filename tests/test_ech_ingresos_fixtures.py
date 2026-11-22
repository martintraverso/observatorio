"""F3.1 (#125): fixtures de las series de ingresos del INE y su registro (AC-I18).

Los fixtures son recortes de las planillas originales (solo las celdas de A:H en las filas 1–120 de la hoja), con
valores, fórmulas y notas intactos. Cada uno lleva la URL oficial y el sha256 del original en
tests/fixtures/ech_ingresos/fixtures.yml. Las planillas se leen acá con la biblioteca estándar (zipfile + XML);
el lector del parser lo elige F3.3.
"""

from __future__ import annotations

import importlib.util
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import yaml

from comun.registro import cargar_fuentes, validar_fuente

RAIZ = Path(__file__).resolve().parents[1]
FIX = RAIZ / "tests" / "fixtures" / "ech_ingresos"
REGISTRO = RAIZ / "fuentes" / "ine_ech_ingresos_series.yml"
DOMINIOS_OFICIALES = ("https://www5.ine.gub.uy/", "https://www.gub.uy/instituto-nacional-estadistica/")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
# AC-I9: conjunto mínimo de indicadores, con la planilla de cada uno.
MINIMO = {
    "ECHING07": "ing_hogar_medio_cagu_cvl", "ECHING08": "ing_hogar_medio_sagu_cvl",
    "ECHING09": "ing_hogar_medio_cagu_svl", "ECHING10": "ing_hogar_medio_sagu_svl",
    "ECHING11": "ing_pc_medio_cagu_cvl", "ECHING12": "ing_pc_medio_sagu_cvl",
    "ECHING13": "ing_pc_medio_cagu_svl", "ECHING14": "ing_pc_medio_sagu_svl",
    "ECHINGRESOS2": "ing_hogar_medio_sagu_svl_ene2005", "ECHINGRESOS3": "ing_pc_medio_sagu_svl_ene2005",
}


def leer_hoja(ruta: Path) -> dict[str, dict]:
    """{ref: {'valor': str|None, 'formula': str|None}} de la única hoja, con los textos compartidos resueltos."""
    with zipfile.ZipFile(ruta) as z:
        hojas = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet")]
        assert hojas == ["xl/worksheets/sheet1.xml"], hojas
        textos = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                textos.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        celdas = {}
        for c in ET.fromstring(z.read(hojas[0])).iter(f"{{{NS['m']}}}c"):
            v, f = c.find("m:v", NS), c.find("m:f", NS)
            valor = v.text if v is not None else None
            if valor is not None and c.get("t") == "s":
                valor = textos[int(valor)]
            # Las fórmulas compartidas (<f t="shared" si="0"/>) no tienen texto: cuentan como fórmula igual.
            celdas[c.get("r")] = {"valor": valor, "formula": (f.text or "") if f is not None else None}
    return celdas


def fila_de(celdas: dict, etiqueta: str) -> int:
    filas = [int(ref[1:]) for ref, c in celdas.items() if ref.startswith("A") and (c["valor"] or "").strip() == etiqueta]
    assert len(filas) == 1, (etiqueta, filas)
    return filas[0]


def redondo(celdas: dict, ref: str) -> int:
    return round(float(celdas[ref]["valor"]))


@pytest.fixture(scope="module")
def fixtures():
    return yaml.safe_load((FIX / "fixtures.yml").read_text(encoding="utf-8"))["archivos"]


@pytest.fixture(scope="module")
def registro():
    return yaml.safe_load(REGISTRO.read_text(encoding="utf-8"))


def test_tres_fixtures_con_procedencia(fixtures, registro):
    assert [f["codigo"] for f in fixtures] == ["ECHING07", "ECHING09", "ECHINGRESOS2"]
    urls = {a["codigo"]: a["url"] for a in registro["archivos"]}
    for f in fixtures:
        assert (FIX / f["archivo"]).is_file()
        assert f["url"].startswith(DOMINIOS_OFICIALES) and f["pagina"].startswith(DOMINIOS_OFICIALES)
        assert f["url"] == urls[f["codigo"]], "la URL del fixture es la del registro"
        assert re.fullmatch(r"[0-9a-f]{64}", f["sha256_original"])
        assert f["bytes_recorte"] < 50_000 < f["bytes_original"]


@pytest.mark.parametrize("codigo", ["ECHING07", "ECHING09", "ECHINGRESOS2"])
def test_fixture_conserva_el_formato(codigo):
    """Título, encabezado en dos filas, 53 períodos (2016–2025 y tres trimestres de 2026), totales como fórmula
    con su valor calculado y notas al pie, como en el original."""
    c = leer_hoja(FIX / f"{codigo}.xlsx")
    assert all(re.fullmatch(r"[A-H]\d+", ref) and int(ref[1:]) <= 120 for ref in c), "solo A:H, filas 1–120"
    assert c["A6"]["valor"].strip() == "Mes, Trimestre y Año"
    assert [c[r]["valor"].strip() for r in ("B6", "C6", "D6", "E6", "F6", "E7", "F7")][1:] == [
        "Montevideo", "Total", "Localidades de", "Localidades Pequeñas", "5.000 o más hab.", "y Zonas rurales"]
    assert c["B6"]["valor"] in ("Total Pais", "Total País")
    assert c["D5"]["valor"] == "Interior"
    etiquetas = [x["valor"] for ref, x in c.items() if ref.startswith("A") and x["valor"]]
    periodos = [e for e in etiquetas if re.match(r"(Enero|Abril|Julio|Octubre) - |Total \d{4}$", e)]
    assert len(periodos) == 53
    totales = [ref for ref, x in c.items() if ref[0] in "BCDEF" and x["formula"] is not None]
    assert len(totales) == 50 and all(c[r]["valor"] for r in totales), "10 totales × 5 columnas, con valor"
    assert "Las cifras presentadas están sujetas a revisión, en función del cierre anual de la base." in etiquetas
    assert any(e.startswith("(1): Cifras actualizadas a") for e in etiquetas)


def test_valores_de_referencia_ac_i11():
    """Los valores que AC-I11 usa como tests dorados están en los fixtures (redondeados)."""
    c = leer_hoja(FIX / "ECHING07.xlsx")
    assert (redondo(c, f"B{fila_de(c, 'Enero - Marzo/16')}")) == 59534
    for anio, pais, mvd in [(2016, 58072, 69557), (2023, 96230, 118532), (2025, 110097, 133145)]:
        f = fila_de(c, f"Total {anio}")
        assert (redondo(c, f"B{f}"), redondo(c, f"C{f}")) == (pais, mvd)
        assert c[f"B{f}"]["formula"] is not None, "el total anual es una fórmula de la planilla"
    c = leer_hoja(FIX / "ECHING09.xlsx")
    f = fila_de(c, "Total 2016")
    assert (redondo(c, f"B{f}"), redondo(c, f"C{f}")) == (49809, 59404)


def test_registro_ac_i18(registro):
    assert validar_fuente(registro, "ine_ech_ingresos_series.yml") == []
    assert "ine_ech_ingresos_series" in cargar_fuentes(RAIZ / "fuentes")
    assert registro["estado"] in ("en preparación", "activa")  # activa desde el 2026-11-21
    assert registro["pagina"].startswith(DOMINIOS_OFICIALES)
    for a in registro["archivos"]:
        assert {"codigo", "titulo", "url", "indicador"} <= set(a), a
        assert a["url"].startswith(DOMINIOS_OFICIALES)
    indicadores = {a["codigo"]: a["indicador"] for a in registro["archivos"]}
    assert {k: indicadores.get(k) for k in MINIMO} == MINIMO
    assert set(registro["columnas"].values()) == {
        "pais/UY", "departamento/01", "region/interior", "region/interior-5000", "region/interior-menores"}
    assert registro["frecuencia"] and len(registro["bases_de_precios"]) >= 2
    assert registro["notas_al_pie"] and registro["cambio_2025_yda"] and registro["variante_titular"] == "sagu_svl"
    assert registro["licencia"] and registro["cita"]
    assert registro["notas_internas"], "decisiones del mantenedor en notas_internas (no se publican, AC-V19)"


def test_recorte_deja_solo_a_h():
    spec = importlib.util.spec_from_file_location("crear", RAIZ / "scripts" / "crear_fixtures_ech_ingresos.py")
    crear = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(crear)
    xml = ('<worksheet><dimension ref="A1:XFD200"/><sheetData>'
           '<row r="1" spans="1:16384"><c r="A1" t="s"><v>0</v></c><c r="H1" s="2"/><c r="I1" s="3"/>'
           '<c r="AA1"><f>+1</f><v>1</v></c></row>'
           '<row r="121" spans="2:3"><c r="B121" s="5"/></row></sheetData></worksheet>')
    assert crear.recortar_hoja(xml) == ('<worksheet><dimension ref="A1:H1"/><sheetData>'
                                        '<row r="1" spans="1:8"><c r="A1" t="s"><v>0</v></c><c r="H1" s="2"/></row>'
                                        '</sheetData></worksheet>')
