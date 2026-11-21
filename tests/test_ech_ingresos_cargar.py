"""F3.4b (#138): carga de las series de ingresos en las tablas del observatorio (AC-I5 reporte, AC-I6).

Sobre una copia de la salida del Censo (fixture o completa, ya con el nivel region) y originales capturados con
F3.4a desde un sitio falso armado con los fixtures de F3.1.
"""

from __future__ import annotations

import io
import shutil
import urllib.error
import zipfile
from pathlib import Path

import ech_ingresos_cargar
import pandas as pd
import pytest
from ech_ingresos_captura import Planilla, capturar
from ech_ingresos_cargar import FUENTE_ID

FIX = Path(__file__).resolve().parent / "fixtures" / "ech_ingresos"
BASE = "https://www5.ine.gub.uy/documents/ingresos/"
PAIS = "INE-2023/pais/UY"
CODIGOS = ["ECHING07", "ECHING08", "ECHING09"]  # ECHING08 no está en el sitio falso: HTTP 404


def p(codigo):
    return Planilla(codigo, BASE + f"{codigo}.xlsx")


def sitio(archivos):
    def bajar(url):
        if url not in archivos:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return archivos[url]
    return bajar


def fix(codigo):
    return (FIX / f"{codigo}.xlsx").read_bytes()


def revisada(xlsx: bytes) -> bytes:
    """Una revisión del INE: el mismo xlsx con el país de Enero - Marzo/16 cambiado (59534,0027… -> 60000)."""
    entrada, salida = zipfile.ZipFile(io.BytesIO(xlsx)), io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for info in entrada.infolist():
            datos = entrada.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                viejo = b"<v>59534.00275705033</v>"
                assert viejo in datos
                datos = datos.replace(viejo, b"<v>60000</v>", 1)
            z.writestr(info, datos)
    return salida.getvalue()


@pytest.fixture
def entorno(salida, tmp_path):
    """(crudo, salida): copia de las tablas del Censo y ECHING07 y ECHING09 capturadas (ECHING08 dio 404)."""
    copia = tmp_path / "salida"

    def ignorar(carpeta, nombres):  # solo tablas y carpetas de fuentes (nada de web ni descargas)
        return [] if Path(carpeta) != Path(salida) else [n for n in nombres if (Path(carpeta) / n).is_dir()
                                                          and n != "fuentes" or n.endswith(".pmtiles")]
    shutil.copytree(salida, copia, ignore=ignorar)
    (copia / "reporte_validacion.md").write_text("# Reporte\n", encoding="utf-8")
    crudo = tmp_path / "crudo"
    capturar([p(c) for c in CODIGOS], crudo, sitio({p(c).url: fix(c) for c in ("ECHING07", "ECHING09")}), hoy="2026-11-21")
    return crudo, copia


def correr(crudo, salida, *extra):
    assert ech_ingresos_cargar.main([str(crudo / "ech_ingresos"), "--salida", str(salida), *extra]) == 0


def obs_ingresos(salida):
    o = pd.read_parquet(salida / "observaciones.parquet")
    c = pd.read_parquet(salida / "capturas.parquet")
    return o[o.captura_id.isin(c[c.fuente_id == FUENTE_ID].id)]


def test_se_carga_junto_al_censo_con_su_captura(entorno):
    crudo, salida = entorno
    antes = pd.read_parquet(salida / "observaciones.parquet")
    correr(crudo, salida)
    o = obs_ingresos(salida)
    assert set(o.indicador) == {"ing_hogar_medio_cagu_cvl", "ing_hogar_medio_cagu_svl"}
    assert len(o) == 2 * 53 * 5
    assert len(pd.read_parquet(salida / "observaciones.parquet")) == len(antes) + len(o)  # el Censo no cambia
    cap = pd.read_parquet(salida / "capturas.parquet").set_index("id")
    assert set(cap.loc[o.captura_id.unique()].url) == {p("ECHING07").url, p("ECHING09").url}
    ind = pd.read_parquet(salida / "indicadores.parquet").set_index("codigo")
    assert ind.loc["ing_hogar_medio_cagu_cvl", "unidad"] == "pesos corrientes por mes"
    assert ind.loc["ing_hogar_medio_cagu_cvl", "tema"] == "Ingresos"
    assert set(o.territorio_id.str.split("/").str[1]) == {"pais", "departamento", "region"}


def test_sin_cambios_no_se_vuelve_a_parsear(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    r = ech_ingresos_cargar.cargar(crudo, salida, ech_ingresos_cargar.fuentes_registro())
    assert r["resultado"] == "sin cambios" and r["parseadas"] == 0


# AC-I6: una revisión reemplaza los valores y el reporte dice cuántos cambiaron y el cambio más grande
def test_una_revision_reemplaza_los_valores_y_se_resume(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    capturar([p("ECHING07")], crudo, sitio({p("ECHING07").url: revisada(fix("ECHING07"))}), hoy="2026-12-15")
    correr(crudo, salida)
    o = obs_ingresos(salida)
    fila = o[(o.indicador == "ing_hogar_medio_cagu_cvl") & (o.territorio_id == PAIS) & (o.periodo == "2016-T1")]
    assert fila.valor.tolist() == [60000.0]  # un solo valor: el de la captura vigente
    cap = pd.read_parquet(salida / "capturas.parquet")
    del07 = cap[cap.url == p("ECHING07").url].sort_values("descargado")
    assert del07.vigente.tolist() == [False, True]
    assert set(o[o.indicador == "ing_hogar_medio_cagu_cvl"].captura_id) == {del07.id.iloc[-1]}
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert "1 valor cambió" in reporte and "2016-T1" in reporte and "+466" in reporte
    assert "Valores que ya no vienen: 0." in reporte


def test_resumen_de_cambios():
    k = ["indicador", "territorio_id", "periodo"]
    antes = pd.DataFrame([["a", "t", "2016-T1", 100.0], ["a", "t", "2016-T2", 200.0]], columns=[*k, "valor"])
    ahora = pd.DataFrame([["a", "t", "2016-T1", 100.0], ["a", "t", "2016-T2", 150.0], ["a", "t", "2016-T3", 5.0]],
                         columns=[*k, "valor"])
    r = ech_ingresos_cargar.resumen_cambios(antes, ahora)
    assert (r["cambiaron"], r["nuevos"], r["quitados"]) == (1, 1, 0)
    assert ech_ingresos_cargar.resumen_cambios(ahora, antes.iloc[:1])["quitados"] == 2
    assert r["mayor"] == {"indicador": "a", "territorio_id": "t", "periodo": "2016-T2", "antes": 200.0, "ahora": 150.0}


# AC-I5: la planilla con error se informa en el reporte y las demás se cargan
def test_el_reporte_lista_las_planillas_con_error(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert "## Ingresos (ECH)" in reporte
    assert "ECHING08" in reporte and "404" in reporte
    assert "ECHING07" in reporte and "ECHING09" in reporte
    # volver a correr no duplica la sección
    correr(crudo, salida)
    assert (salida / "reporte_validacion.md").read_text(encoding="utf-8").count("## Ingresos (ECH)") == 1


def test_sin_capturas_falla(tmp_path, entorno):
    _, salida = entorno
    with pytest.raises(ech_ingresos_cargar.ErrorCarga, match="capturas"):
        ech_ingresos_cargar.cargar(tmp_path / "vacio", salida, ech_ingresos_cargar.fuentes_registro())
