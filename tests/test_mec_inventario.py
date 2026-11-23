"""F4.1 (#164): registro del anuario del MEC y fixtures (AC-E1, AC-E2)."""

import re
import zipfile
from pathlib import Path

import yaml

from comun.registro import validar_fuente

RAIZ = Path(__file__).resolve().parents[1]
REG = yaml.safe_load((RAIZ / "fuentes" / "mec_anuario_educacion.yml").read_text(encoding="utf-8"))
FIXTURES = RAIZ / "tests" / "fixtures" / "mec_anuario"


def hojas(xlsx: Path) -> set[str]:
    with zipfile.ZipFile(xlsx) as z:
        wb = z.read("xl/workbook.xml").decode("utf-8")
    return {n.strip() for n in re.findall(r'<sheet [^>]*name="([^"]+)"', wb)}


def test_registro_valida_y_queda_en_preparacion():
    assert validar_fuente(REG, "mec_anuario_educacion.yml") == []
    assert REG["estado"] == "en preparación"


def test_ac_e1_un_anuario_por_anio_desde_la_pagina_oficial():
    assert sorted(REG["anuarios"]) == [2020, 2021, 2022, 2023, 2024]
    for a, f in REG["anuarios"].items():
        assert f["pagina"].startswith("https://www.gub.uy/ministerio-educacion-cultura/"), a
        assert f["url"].startswith("https://www.gub.uy/ministerio-educacion-cultura/sites/"), a
        assert re.fullmatch(r"[0-9a-f]{64}", f["sha256"]), a
        assert f["publicado"], a


def test_ac_e2_cada_cuadro_tiene_tipo_ola_y_mapeo_en_la_ola_1():
    assert len([c for c, e in REG["cuadros"].items() if 2024 in e["anios"]]) == 110
    assert len([c for c, e in REG["cuadros"].items() if 2023 in e["anios"]]) == 107
    for cod, e in REG["cuadros"].items():
        assert set(e["tipo"].split("/")) <= {"A", "B", "C"}, cod
        assert e["ola"] in (1, 2), cod
        if e["ola"] == 1:
            assert set(e["mapeo"]) == set(e["anios"]), cod


def test_ii_2_2_1_el_sexo_de_2024_es_otro_indicador_que_el_de_2023():
    m = REG["cuadros"]["II-2.2.1"]["mapeo"]
    ruta = "FORMA DE ADMINISTRACIÓN/TOTAL/MUJER"
    assert m[2023][ruta] != m[2024][ruta]
    assert m[2023]["TOTAL"] == m[2024]["TOTAL"]


def test_fixtures_tienen_la_ola_1_la_serie_y_cuadros_b_y_c():
    ola1 = {c for c, e in REG["cuadros"].items() if e["ola"] == 1}
    for anio in (2024, 2023):
        h = hojas(FIXTURES / f"{anio}.xlsx")
        presentes = {c for c in ola1 if anio in REG["cuadros"][c]["anios"]}
        assert presentes <= h, presentes - h
        assert any(x.startswith("MATRÍCULA DEL SISTEMA") for x in h)
        tipos = [REG["cuadros"][c]["tipo"] for c in h if c in REG["cuadros"]]
        assert sum(t == "B" for t in tipos) >= 2 and sum("C" in t for t in tipos) >= 2
