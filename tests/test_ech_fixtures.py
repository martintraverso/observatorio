"""F2.1 (#40): fixtures de los informes de mercado de trabajo del INE y su registro (AC-L20).

Los fixtures son recortes de los HTML originales (sin <script>, <style> ni imágenes data:), con las tablas y el
texto intactos. Cada uno lleva la URL oficial y el sha256 del original en tests/fixtures/ech_mt/fixtures.yml.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from comun.registro import cargar_fuentes

RAIZ = Path(__file__).resolve().parents[1]
FIX = RAIZ / "tests" / "fixtures" / "ech_mt"
REGISTRO = RAIZ / "fuentes" / "ine_ech_mercado_trabajo_departamental.yml"
DOMINIOS_OFICIALES = ("https://www5.ine.gub.uy/", "https://www.gub.uy/instituto-nacional-estadistica/")


class Tablas(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tablas, self.fila, self.celda = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tablas.append([])
        elif tag == "tr" and self.tablas:
            self.fila = []
        elif tag in ("td", "th") and self.fila is not None:
            self.celda = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.celda is not None:
            self.fila.append(" ".join(" ".join(self.celda).split()))
            self.celda = None
        elif tag == "tr" and self.fila is not None:
            self.tablas[-1].append(self.fila)
            self.fila = None

    def handle_data(self, data):
        if self.celda is not None:
            self.celda.append(data)


def tablas(nombre: str) -> list[list[list[str]]]:
    p = Tablas()
    p.feed((FIX / nombre).read_text(encoding="utf-8"))
    return p.tablas


@pytest.fixture(scope="module")
def indice() -> list[dict]:
    return yaml.safe_load((FIX / "fixtures.yml").read_text(encoding="utf-8"))["informes"]


def test_tres_informes_de_distintas_epocas_con_su_origen(indice):
    assert [i["periodo_fin"] for i in indice] == ["2022-02", "2024-09", "2026-09"]
    for i in indice:
        assert (FIX / i["archivo"]).exists(), i["archivo"]
        assert i["url"].startswith(DOMINIOS_OFICIALES) and i["pagina"].startswith(DOMINIOS_OFICIALES)
        assert len(i["sha256_original"]) == 64 and i["bytes_original"] > 1_000_000
        assert (FIX / i["archivo"]).stat().st_size < 100_000  # recorte liviano


@pytest.mark.parametrize("archivo,con_totales", [
    ("ech_mt_2022_02.html", False), ("ech_mt_2024_09.html", False), ("ech_mt_2026_09.html", True)])
def test_seis_cuadros_legibles_con_departamentos_y_municipios(archivo, con_totales):
    t = tablas(archivo)
    assert len(t) == 6
    for k in range(6):
        cuerpo = [f for f in t[k][1:] if not f[0].startswith("Fuente")]
        es_depto = k < 3
        nombres = [f[0] for f in cuerpo]
        esperado = (19 if es_depto else 8) + (1 if con_totales else 0)
        assert len(cuerpo) == esperado, (archivo, k, nombres)
        assert ("Total país" in nombres if es_depto else "Total Montevideo" in nombres) is con_totales
        assert all(any(c.isdigit() for c in v) for f in cuerpo for v in f[1:]), (archivo, k)


def test_valores_del_informe_jul_set_2026_ac_l8():
    filas = {f[0]: f[1:] for f in tablas("ech_mt_2026_09.html")[0]}
    assert filas["Total país"] == ["64,1", "59,5", "7,1"]
    assert filas["Montevideo"] == ["65,5", "60,8", "7,2"]
    assert filas["Maldonado"] == ["69,1", "65,3", "5,5"]
    assert filas["Treinta y Tres"] == ["54,1", "48,6", "10,2"]


def test_registro_de_la_fuente_ac_l20():
    f = cargar_fuentes(RAIZ / "fuentes")["ine_ech_mercado_trabajo_departamental"]
    assert f["estado"] == "activa" and f["temas"] == ["Trabajo"]  # activa desde #69
    for clave in ("patrones_url", "descubrimiento", "periodo", "cuadros", "formatos", "advertencias", "cita"):
        assert f.get(clave), clave
    assert len(f["cuadros"]) == 6 and len(f["advertencias"]) >= 5
    assert all(u.startswith(DOMINIOS_OFICIALES) for u in (f["pagina"], f["url_descarga"]))
