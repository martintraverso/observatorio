"""F4.5b (#189, AC-E23): control cruzado con el Anuario Estadístico Nacional del INE (cap. 3.1). Advertencia: los
valores del INE nunca se cargan. Fixtures: las tablas 3.1.6 (por departamento) y 3.1.2 (sin departamentos) tal como
las publica el INE.
"""

from __future__ import annotations

import hashlib
import json

import mec_ine_control as ic
import pytest
from test_mec_cargar import FIX, RAIZ, correr, tablas

INE = FIX / "ine"
PAGINA = """<a href="https://www5.ine.gub.uy/documents/ANUARIOS/Anuario 2025/3 - ASPECTOS SOCIALES/3.1 Educación/3.1.6ok.xls">3.1.6</a>
<a href="https://www5.ine.gub.uy/documents/ANUARIOS/Anuario 2025/3 - ASPECTOS SOCIALES/3.1 Educación/3.1.2ok.xls">3.1.2</a>"""


def tabla_316():
    return ic.leer_tabla((INE / "3.1.6.xls").read_bytes(), "3.1.6")


def test_lee_una_tabla_del_ine_por_anio_territorio_y_columna():
    t = tabla_316()
    assert set(t.anio) == {"2023", "2024"} and t.territorio_id.nunique() == 21
    assert t.columna.nunique() == 8
    v = t.set_index(["anio", "territorio_id", "columna"]).valor
    assert v[("2024", "INE-2023/pais/UY", "General/Pública/Hombres")] == 50776
    assert v[("2024", "INE-2023/departamento/02", "General/Pública/Hombres")] == 1316  # Artigas
    assert v[("2024", "INE-2023/region/interior", "General/Pública/Mujeres")] == 38076


def test_una_tabla_sin_departamentos_no_se_compara():
    with pytest.raises(ValueError):
        ic.leer_tabla((INE / "3.1.2.xls").read_bytes(), "3.1.2")  # años en columnas, filas por categoría


def test_captura_solo_de_sitios_oficiales_y_sin_cambios(tmp_path):
    archivos = {"3.1.6": (INE / "3.1.6.xls").read_bytes(), "3.1.2": (INE / "3.1.2.xls").read_bytes()}

    def bajar(url):
        assert url.startswith(ic.OFICIAL)
        if url == ic.PAGINA:
            return PAGINA.encode("utf-8")
        return archivos[url.rsplit("/", 1)[1].replace("ok.xls", "")]
    m = ic.capturar(tmp_path, bajar, hoy="2026-11-24")
    assert set(m["tablas"]) == {"3.1.6", "3.1.2"}
    assert (tmp_path / ic.CARPETA / "3.1.6.xls").read_bytes() == archivos["3.1.6"]
    assert m["tablas"]["3.1.6"]["sha256"] == hashlib.sha256(archivos["3.1.6"]).hexdigest()
    assert {e["tabla"] for e in m["errores"]} == set(ic.TABLAS) - {"3.1.6", "3.1.2"}
    with pytest.raises(ValueError):
        ic.bajar("https://ejemplo.com/3.1.6.xls")


def correspondencias():
    import yaml

    return yaml.safe_load((RAIZ / "fuentes" / "mec_anuario" / "mapeo_manual.yml").read_text(encoding="utf-8"))["control_ine"]


def test_compara_con_el_mapeo_del_registro_y_lista_toda_diferencia(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    obs, _, ind = tablas(salida)
    pct = set(ind[ind.es_derivado].codigo)
    ine = tabla_316()
    r = ic.comparar(ine, obs, correspondencias(), pct)
    assert "3.1.6 «Vocacional/Pública/Hombres» = `edu_ii_3_2_2_publica_sexo_v`" in r["pares"]
    assert r["diferencias"] == [] and r["comparados"] >= 2 * 2 * 21  # V y M públicas, dos años, 21 territorios
    # una diferencia en el país también se lista (no deja a la columna «sin par»)
    for terr in ("INE-2023/pais/UY", "INE-2023/departamento/02"):
        cambiada = ine.copy()
        fila = (cambiada.anio == "2024") & (cambiada.territorio_id == terr) & (cambiada.columna == "Vocacional/Pública/Hombres")
        cambiada.loc[fila, "valor"] += 5
        r = ic.comparar(cambiada, obs, correspondencias(), pct)
        assert len(r["diferencias"]) == 1 and r["diferencias"][0].startswith(f"3.1.6 «Vocacional/Pública/Hombres» 2024 {terr.split('/', 1)[1]}")


def test_una_columna_sin_correspondencia_y_un_codigo_por_anio():
    ine = tabla_316()
    obs = ine[ine.columna == "Vocacional/Pública/Hombres"].assign(
        indicador=lambda d: d.anio.map({"2023": "x_2023", "2024": "x_2024"}), periodo=lambda d: d.anio)
    r = ic.comparar(ine, obs[["indicador", "territorio_id", "periodo", "valor"]],
                    {"3.1.6": {"Vocacional/Pública/Hombres": {2023: "x_2023", 2024: "x_2024"}}}, set())
    assert r["diferencias"] == [] and r["comparados"] == 42
    assert len(r["sin_par"]) == 7  # las otras columnas de 3.1.6


def test_la_carga_reporta_el_control_y_no_carga_valores_del_ine(entorno):
    crudo, salida = entorno
    d = crudo / ic.CARPETA
    d.mkdir(parents=True)
    tablas_ = {}
    for t in ("3.1.6", "3.1.2"):
        datos = (INE / f"{t}.xls").read_bytes()
        (d / f"{t}.xls").write_bytes(datos)
        tablas_[t] = {"url": f"https://www5.ine.gub.uy/{t}.xls", "archivo": f"{t}.xls", "sha256": hashlib.sha256(datos).hexdigest()}
    (d / "control_ine.json").write_text(json.dumps({"pagina": ic.PAGINA, "fecha": "2026-11-24", "tablas": tablas_, "errores": []}))
    correr(crudo, salida)
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert "### Control con el Anuario Estadístico Nacional del INE (AC-E23, advertencia)" in reporte
    assert "diferencias: 0." in reporte and "No comparables por territorio: 3.1.2." in reporte
    con_ine = tablas(salida)[0].drop(columns="captura_id").sort_values(["indicador", "territorio_id", "periodo"])
    import shutil

    shutil.rmtree(d)  # sin las tablas del INE, lo publicado es idéntico: el control no carga nada
    correr(crudo, salida, "--forzar")
    sin_ine = tablas(salida)[0].drop(columns="captura_id").sort_values(["indicador", "territorio_id", "periodo"])
    assert con_ine.reset_index(drop=True).equals(sin_ine.reset_index(drop=True))


def test_una_tabla_que_no_se_puede_leer_no_corta_la_carga(entorno):
    crudo, salida = entorno
    d = crudo / ic.CARPETA
    d.mkdir(parents=True)
    roto = b"no es una planilla"
    (d / "3.1.6.xls").write_bytes(roto)
    (d / "control_ine.json").write_text(json.dumps({"pagina": ic.PAGINA, "fecha": "2026-11-24", "errores": [], "tablas": {
        "3.1.6": {"url": "https://www5.ine.gub.uy/3.1.6.xls", "archivo": "3.1.6.xls", "sha256": hashlib.sha256(roto).hexdigest()}}}))
    correr(crudo, salida)
    assert "3.1.6: no se pudo leer" in (salida / "reporte_validacion.md").read_text(encoding="utf-8")


def test_sin_tablas_del_ine_el_control_no_corre(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    assert "el control no corrió" in (salida / "reporte_validacion.md").read_text(encoding="utf-8")


@pytest.fixture
def entorno(salida, tmp_path):
    """(crudo, salida) como en test_mec_cargar: Censo copiado y anuarios 2023 y 2024 capturados."""
    import shutil
    from pathlib import Path

    from mec_anuario_captura import capturar_anuarios
    from test_ech_cargar import completar_departamentos
    from test_mec_cargar import FUENTE, URL, fix, sitio

    copia = tmp_path / "salida"

    def ignorar(carpeta, nombres):
        return [] if Path(carpeta) != Path(salida) else [n for n in nombres if (Path(carpeta) / n).is_dir()
                                                          and n != "fuentes" or n.endswith(".pmtiles")]
    shutil.copytree(salida, copia, ignore=ignorar)
    (copia / "reporte_validacion.md").write_text("# Reporte\n", encoding="utf-8")
    completar_departamentos(copia)
    crudo = tmp_path / "crudo"
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: fix(2024)}), hoy="2026-11-23")
    return crudo, copia

