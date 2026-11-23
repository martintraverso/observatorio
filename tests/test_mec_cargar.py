"""F4.4 (#167): captura y carga de los anuarios del MEC (AC-E4…E7, AC-E16).

Sobre una copia de la salida del Censo (con el nivel region) y anuarios capturados desde un sitio falso armado con
los fixtures de F4.1 (2024 y 2023; 2020–2022 dan HTTP 404).
"""

from __future__ import annotations

import io
import json
import re
import shutil
import urllib.error
import zipfile
from pathlib import Path

import mec_anuario_cargar
import pandas as pd
import pytest
import yaml
from mec_anuario_captura import FUENTE_ID, capturar_anuarios
from test_ech_cargar import completar_departamentos

from comun.xlsx import _hojas

RAIZ = Path(__file__).resolve().parents[1]
FIX = RAIZ / "tests" / "fixtures" / "mec_anuario"
FUENTE = yaml.safe_load((RAIZ / "fuentes" / "mec_anuario_educacion.yml").read_text(encoding="utf-8"))
URL = {a: f["url"] for a, f in FUENTE["anuarios"].items()}
PAIS = "INE-2023/pais/UY"


def sitio(archivos: dict):
    def bajar(url):
        if url not in archivos:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return archivos[url]
    return bajar


def fix(anio):
    return (FIX / f"{anio}.xlsx").read_bytes()


def con_valor(xlsx: bytes, cuadro: str, celda: str, valor: int) -> bytes:
    """El mismo anuario con una celda numérica de un cuadro cambiada (una revisión del MEC)."""
    entrada = zipfile.ZipFile(io.BytesIO(xlsx))
    hoja = next(r for n, r in _hojas(entrada).items() if n.strip() == cuadro)
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for info in entrada.infolist():
            datos = entrada.read(info.filename)
            if info.filename == hoja:
                texto, n = re.subn(rf'(<c r="{celda}"[^>]*>(?:<f>.*?</f>)?<v>)[^<]*(</v>)', rf"\g<1>{valor}\g<2>",
                                   datos.decode("utf-8"), count=1)
                assert n == 1
                datos = texto.encode("utf-8")
            z.writestr(info, datos)
    return salida.getvalue()


@pytest.fixture
def entorno(salida, tmp_path):
    copia = tmp_path / "salida"

    def ignorar(carpeta, nombres):
        return [] if Path(carpeta) != Path(salida) else [n for n in nombres if (Path(carpeta) / n).is_dir()
                                                          and n != "fuentes" or n.endswith(".pmtiles")]
    shutil.copytree(salida, copia, ignore=ignorar)
    (copia / "reporte_validacion.md").write_text("# Reporte\n", encoding="utf-8")
    completar_departamentos(copia)  # el fixture del Censo trae 4 departamentos; el anuario publica los 19
    crudo = tmp_path / "crudo"
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: fix(2024)}), hoy="2026-11-23")
    return crudo, copia


def correr(crudo, salida, *extra):
    assert mec_anuario_cargar.main([str(crudo / "mec_anuario"), "--salida", str(salida), *extra]) == 0


def tablas(salida):
    o = pd.read_parquet(salida / "observaciones.parquet")
    c = pd.read_parquet(salida / "capturas.parquet")
    c = c[c.fuente_id == FUENTE_ID]
    i = pd.read_parquet(salida / "indicadores.parquet")
    return o[o.captura_id.isin(c.id)], c, i[i.fuente_id == FUENTE_ID]


def valor(o, ind, territorio=PAIS, periodo="2024"):
    f = o[(o.indicador == ind) & (o.territorio_id == territorio) & (o.periodo == periodo)]
    assert len(f) == 1, (ind, territorio, periodo)
    return f.valor.iloc[0]


def test_ac_e4_cada_anio_es_una_captura_guardada_sin_cambios(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    assert (crudo / "mec_anuario" / "2024.xlsx").read_bytes() == fix(2024)
    registro = json.loads((crudo / "mec_anuario" / "capturas.json").read_text(encoding="utf-8"))
    por_anio = {c["codigo"]: c for c in registro["capturas"]}
    assert set(por_anio) == {"2023", "2024"}
    assert por_anio["2024"]["url"] == URL[2024] and por_anio["2024"]["descargado"] == "2026-11-23"
    o, c, _ = tablas(salida)
    assert set(c.url) == {URL[2023], URL[2024]} and c.vigente.all()
    assert set(o.periodo) >= {"2023", "2024"}


def test_ac_e5_un_anio_con_error_se_reporta_y_los_demas_se_cargan(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert "## Educación (MEC" in reporte
    assert "**2020**" in reporte and "404" in reporte
    o, _, _ = tablas(salida)
    assert valor(o, "edu_ii_2_2_1_total") == 284944 and valor(o, "edu_ii_2_2_1_total", periodo="2023") == 287805


def test_ac_e6_sin_cambios_no_recarga_y_una_revision_reemplaza_su_anio(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    assert mec_anuario_cargar.cargar(crudo, salida, mec_anuario_cargar.cargar_fuentes(RAIZ / "fuentes"))["resultado"] == "sin cambios"
    revisado = con_valor(fix(2024), "II-2.2.1", "B12", 7300)  # Artigas 7.209 → 7.300
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: revisado}), hoy="2026-11-30")
    correr(crudo, salida)
    o, c, _ = tablas(salida)
    assert valor(o, "edu_ii_2_2_1_total", "INE-2023/departamento/02") == 7300
    assert len(c) == 3 and c.vigente.sum() == 2  # la captura anterior de 2024 queda, no vigente
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert re.search(r"Cambios: \d+ valores cambiaron", reporte) and "7.209 → 7.300" in reporte


def test_ac_e7_la_serie_sale_del_ultimo_anuario_y_una_diferencia_es_advertencia(entorno):
    crudo, salida = entorno
    revisado = con_valor(fix(2024), "II-2.2.1", "B9", 284000)  # el cuadro ya no coincide con la serie (284.944)
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: revisado}), hoy="2026-11-30")
    correr(crudo, salida)
    o, _, _ = tablas(salida)
    serie = "edu_serie_total_educacion_primaria_primaria_comun"
    assert valor(o, serie) == 284944 and valor(o, "edu_ii_2_2_1_total") == 284000  # se guardan los dos
    assert valor(o, serie, periodo="2002") > 0 and valor(o, "edu_serie_total_sistema") == 1042564
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert "2024: la serie nacional dice 284.944 y edu_ii_2_2_1_total dice 284.000" in reporte


def test_ac_e16_tasas_derivadas(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    o, _, i = tablas(salida)
    tasa = "edu_ii_2_2_13_rendimiento_escolar_tasa_promocion_total"
    assert round(valor(o, tasa), 2) == 97.97  # 232.567 / (232.567 + 4.818)
    fila = i.set_index("codigo").loc[tasa]
    assert fila.es_derivado and fila.unidad == "%" and "promovidos" in fila.formula
    assert round(valor(o, "edu_ii_2_2_1_pct_privada"), 2) == round(47559 / 284944 * 100, 2)
    publicados = i[~i.es_derivado]
    assert (publicados.formula == "").all() and set(publicados.unidad) <= {"estudiantes", "establecimientos", "docentes", "grupos"}


def test_resto_del_pais_va_a_la_region_interior(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    o, _, _ = tablas(salida)
    assert valor(o, "edu_ii_2_2_1_total", "INE-2023/region/interior") == 182762


def test_ac_e16_sin_uno_de_los_dos_no_hay_tasa():
    obs = pd.DataFrame([
        {"indicador": "edu_ii_2_2_13_x_promovidos_total", "territorio_id": PAIS, "periodo": "2024", "valor": 90,
         "codigo_cuadro": "II-2.2.13"},
        {"indicador": "edu_ii_2_2_13_x_no_promovidos_total", "territorio_id": PAIS, "periodo": "2024", "valor": 10,
         "codigo_cuadro": "II-2.2.13"},
        {"indicador": "edu_ii_2_2_13_x_no_promovidos_rural", "territorio_id": PAIS, "periodo": "2024", "valor": 3,
         "codigo_cuadro": "II-2.2.13"},  # sin «promovidos rural»: no hay tasa
    ])
    d, formulas = mec_anuario_cargar.derivados(obs)
    assert d.set_index("indicador").valor.to_dict() == {"edu_ii_2_2_13_x_tasa_promocion_total": 90.0}


def test_ac_e6_una_revision_solo_parsea_el_anio_que_cambio(entorno, monkeypatch):
    crudo, salida = entorno
    correr(crudo, salida)
    revisado = con_valor(fix(2024), "II-2.2.1", "B12", 7300)
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: revisado}), hoy="2026-11-30")
    leidos = []
    original = mec_anuario_cargar.leer_anuario
    monkeypatch.setattr(mec_anuario_cargar, "leer_anuario", lambda x, a, f: leidos.append(a) or original(x, a, f))
    r = mec_anuario_cargar.cargar(crudo, salida, mec_anuario_cargar.cargar_fuentes(RAIZ / "fuentes"))
    assert leidos == [2024] and r["parseadas"] == 1
    o, _, i = tablas(salida)
    assert valor(o, "edu_ii_2_2_1_total", periodo="2023") == 287805  # 2023 sigue, tomado de lo publicado
    assert i.set_index("codigo").loc["edu_ii_2_2_13_rendimiento_escolar_promovidos_total"].nota  # nota conservada


def test_ac_e6_una_revision_de_un_anio_viejo_deja_el_catalogo_como_una_carga_completa(entorno, tmp_path):
    crudo, salida = entorno
    correr(crudo, salida)
    revisado = con_valor(fix(2023), "II-2.2.1", "B12", 7000)
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: revisado, URL[2024]: fix(2024)}), hoy="2026-11-30")
    copia = tmp_path / "forzada"
    shutil.copytree(salida, copia)
    correr(crudo, salida)  # solo parsea 2023
    correr(crudo, copia, "--forzar")  # parsea todo
    _, _, incremental = tablas(salida)
    _, _, completa = tablas(copia)
    cols = ["codigo", "nombre", "unidad", "nota", "es_derivado", "formula"]
    pd.testing.assert_frame_equal(incremental[cols].sort_values("codigo").reset_index(drop=True),
                                  completa[cols].sort_values("codigo").reset_index(drop=True))
