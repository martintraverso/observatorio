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


def ajustar(xlsx: bytes, cuadro: str, cambios: list[tuple[str, str, int]]) -> bytes:
    """Una revisión coherente del MEC: suma `delta` a la celda (fila con ese rótulo, columna) de cada cambio."""
    import mec_anuario as mec

    celdas, combinadas = mec.celdas_de(xlsx, mec.hoja_del_cuadro(xlsx, cuadro))
    filas = {rot: r for r, rot in mec.estructura(celdas, combinadas, cuadro).filas}
    for rotulo, col, delta in cambios:
        r = filas[rotulo]
        xlsx = con_valor(xlsx, cuadro, f"{col}{r}", int(celdas[(r, mec._col(col))]) + delta)
    return xlsx


def promovidos_revisados(anio: int, delta: int = 10) -> bytes:
    """II-2.2.13: Artigas gana y Canelones pierde `delta` promovidos urbanos (total y urbana): los totales del país
    y las sumas por área siguen cerrando."""
    return ajustar(fix(anio), "II-2.2.13", [("Artigas", "B", delta), ("Artigas", "C", delta),
                                            ("Canelones", "B", -delta), ("Canelones", "C", -delta)])


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
    revisado = promovidos_revisados(2024)  # Artigas +10 promovidos, Canelones −10
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: revisado}), hoy="2026-11-30")
    antes = valor(tablas(salida)[0], "edu_ii_2_2_13_rendimiento_escolar_promovidos_total", "INE-2023/departamento/02")
    correr(crudo, salida)
    o, c, _ = tablas(salida)
    assert valor(o, "edu_ii_2_2_13_rendimiento_escolar_promovidos_total", "INE-2023/departamento/02") == antes + 10
    assert len(c) == 3 and c.vigente.sum() == 2  # la captura anterior de 2024 queda, no vigente
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert re.search(r"Cambios: \d+ valores cambiaron", reporte) and "el cambio más grande" in reporte


def test_ac_e7_la_serie_sale_del_ultimo_anuario_y_una_diferencia_es_advertencia(entorno):
    crudo, salida = entorno
    import mec_anuario as mec

    xlsx = fix(2024)
    hoja = next(h for h in mec.nombres_de_hojas(xlsx) if h.startswith(mec.SERIE))
    filas, _ = mec.leer_hoja(xlsx, hoja)
    r = next(r for r, cols in filas.items() if any(isinstance(v, str) and v.strip() == "Primaria Común" for v in cols.values()))
    c = next(c for c, v in filas[max(k for k in filas if k < r and any(v == 2024.0 for v in filas[k].values()))].items() if v == 2024.0)
    revisado = con_valor(xlsx, hoja.strip(), f"{mec.letra(c)}{r}", 284000)  # la serie ya no coincide con el cuadro
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: revisado}), hoy="2026-11-30")
    correr(crudo, salida)
    o, _, _ = tablas(salida)
    serie = "edu_serie_total_educacion_primaria_primaria_comun"
    assert valor(o, serie) == 284000 and valor(o, "edu_ii_2_2_1_total") == 284944  # se guardan los dos
    assert valor(o, serie, periodo="2002") > 0 and valor(o, "edu_serie_total_sistema") == 1042564
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert "2024: la serie nacional dice 284.000 y edu_ii_2_2_1_total dice 284.944" in reporte


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
    revisado = promovidos_revisados(2024)
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: revisado}), hoy="2026-11-30")
    leidos = []
    original = mec_anuario_cargar.leer_anuario
    monkeypatch.setattr(mec_anuario_cargar, "leer_anuario", lambda x, a, *r: leidos.append(a) or original(x, a, *r))
    r = mec_anuario_cargar.cargar(crudo, salida, mec_anuario_cargar.cargar_fuentes(RAIZ / "fuentes"))
    assert leidos == [2024] and r["parseadas"] == 1
    o, _, i = tablas(salida)
    assert valor(o, "edu_ii_2_2_1_total", periodo="2023") == 287805  # 2023 sigue, tomado de lo publicado
    assert i.set_index("codigo").loc["edu_ii_2_2_13_rendimiento_escolar_promovidos_total"].nota  # nota conservada


def test_ac_e6_una_revision_de_un_anio_viejo_deja_el_catalogo_como_una_carga_completa(entorno, tmp_path):
    crudo, salida = entorno
    correr(crudo, salida)
    revisado = promovidos_revisados(2023)
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


# ---------------------------------------------------------------- F4.5a (#188): controles (AC-E17…E22, E24)

def test_ac_e24_la_seccion_tiene_controles_cuadros_y_ultimos_valores(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    for texto in ("### Controles (AC-E17…AC-E22)", "| AC-E17 Montevideo + 18 departamentos = TOTAL | OK |",
                  "| AC-E19 Desgloses", "| AC-E20 ", "| AC-E21 ", "AC-E22", "### Cuadros (AC-E24)",
                  "Mapeados y cargados (ola 1):", "### Últimos valores", "| Matrícula de primaria común (II-2.2.1) | 2024 | 284.944 | 102.182 |"):
        assert texto in reporte, texto
    # una excepción de la fuente va como advertencia, con su motivo
    assert "II-4.2.13 2023" in reporte and "no es la suma de los departamentos" in reporte


def test_ac_e17_un_departamento_que_no_cierra_frena_la_carga(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    antes = (salida / "observaciones.parquet").read_bytes()
    roto = con_valor(fix(2024), "II-2.2.1", "B12", 7300)  # Artigas sube y el TOTAL no
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: roto}), hoy="2026-11-30")
    with pytest.raises(mec_anuario_cargar.ErrorCarga, match="AC-E17"):
        mec_anuario_cargar.cargar(crudo, salida, mec_anuario_cargar.cargar_fuentes(RAIZ / "fuentes"))
    assert (salida / "observaciones.parquet").read_bytes() == antes  # no se publicó nada


def test_ac_e18_un_resto_del_pais_que_no_cierra_saltea_solo_esa_fila(entorno):
    crudo, salida = entorno
    roto = ajustar(fix(2024), "II-2.2.18", [("RESTO DEL PAÍS", "B", -82)])  # 4.182 → 4.100 ≠ 6.981 − 2.799
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: roto}), hoy="2026-11-30")
    correr(crudo, salida)
    o, _, _ = tablas(salida)
    interior, ind = "INE-2023/region/interior", "edu_ii_2_2_18_asistencia_insuficiente_solo_1_er_ano"
    assert o[(o.indicador == ind) & (o.territorio_id == interior) & (o.periodo == "2024")].empty
    assert valor(o, "edu_ii_2_2_18_asistencia_insuficiente_1_o_a_6_o_anos", interior) == 24194  # las demás columnas siguen
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert "Resto del país 4100 ≠ 6981 − 2799; no se carga la fila del Interior" in reporte


def test_ac_e20_un_conteo_negativo_frena_la_carga(entorno):
    import mec_anuario_controles as mc

    crudo, salida = entorno
    correr(crudo, salida)
    o, _, i = tablas(salida)
    o = o.copy()
    o.loc[o.index[0], "valor"] = -1
    r = mc.controles(o, FUENTE, {}, set(i[i.es_derivado].codigo))
    assert [f["control"] for f in r.controles.fallas][0].startswith("AC-E20")



def test_ac_e19_un_desglose_que_no_cierra_frena_la_carga(entorno):
    crudo, salida = entorno
    roto = ajustar(fix(2024), "II-2.2.1", [("Artigas", "F", 10), ("Canelones", "F", -10)])  # pública varones
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: roto}), hoy="2026-11-30")
    with pytest.raises(mec_anuario_cargar.ErrorCarga, match="AC-E19.*departamento/02"):
        mec_anuario_cargar.cargar(crudo, salida, mec_anuario_cargar.cargar_fuentes(RAIZ / "fuentes"))


def test_ac_e18_un_resto_del_pais_con_desglose_que_no_cierra_no_frena(entorno):
    """La fila del Interior saltada por AC-E18 tampoco la mira AC-E19 (pública = varones + mujeres)."""
    crudo, salida = entorno
    roto = ajustar(fix(2024), "II-2.2.1", [("RESTO DEL PAÍS", "E", -50)])
    capturar_anuarios(crudo, FUENTE, sitio({URL[2023]: fix(2023), URL[2024]: roto}), hoy="2026-11-30")
    correr(crudo, salida)
    o, _, _ = tablas(salida)
    ind = "edu_ii_2_2_1_forma_de_administracion_publica_total"
    assert o[(o.indicador == ind) & (o.territorio_id == "INE-2023/region/interior") & (o.periodo == "2024")].empty
    assert valor(o, "edu_ii_2_2_1_total", "INE-2023/region/interior") == 182762


def test_ac_e18_sin_el_territorio_interior_se_saltean_las_filas_de_region(entorno):
    import geopandas as gpd

    crudo, salida = entorno
    t = gpd.read_parquet(salida / "territorios.parquet")
    t[t.id != "INE-2023/region/interior"].to_parquet(salida / "territorios.parquet")
    for p in ("correspondencias",):
        c = pd.read_parquet(salida / f"{p}.parquet")
        c[(c.origen_id != "INE-2023/region/interior") & (c.destino_id != "INE-2023/region/interior")].to_parquet(salida / f"{p}.parquet")
    o = pd.read_parquet(salida / "observaciones.parquet")
    o[o.territorio_id != "INE-2023/region/interior"].to_parquet(salida / "observaciones.parquet")
    for d in (salida / "fuentes").glob("*"):  # las fuentes que publican región (ingresos) quedan sin ella
        if (d / "observaciones.parquet").exists():
            od = pd.read_parquet(d / "observaciones.parquet")
            od[od.territorio_id != "INE-2023/region/interior"].to_parquet(d / "observaciones.parquet")
    correr(crudo, salida)
    o, _, _ = tablas(salida)
    assert not (o.territorio_id == "INE-2023/region/interior").any() and len(o)
    assert "no existe: se saltean" in (salida / "reporte_validacion.md").read_text(encoding="utf-8")


def test_ac_e21_un_territorio_sin_valor_ni_sin_dato_frena():
    import mec_anuario as mec
    import mec_anuario_controles as mc
    e = FUENTE["cuadros"]["II-2.2.1"]
    c = mec.parsear_cuadro(fix(2024), "II-2.2.1", 2024, e["mapeo"][2024], "A")
    sin_colonia = c.datos[~((c.datos.indicador == "edu_ii_2_2_1_total") & (c.datos.territorio_id == "INE-2023/departamento/05"))]
    fuente = {"cuadros": {"II-2.2.1": e}}
    ok = mc.controles(c.datos, fuente, {}, set(), set(c.sin_dato_claves), {"2024"})
    assert not ok.controles.fallas
    r = mc.controles(sin_colonia, fuente, {}, set(), set(c.sin_dato_claves), {"2024"})
    assert [f["control"] for f in r.controles.fallas if f["control"].startswith("AC-E21")]
    # publicado sin dato («s/d»): no es una falla
    r = mc.controles(sin_colonia, fuente, {}, set(), set(c.sin_dato_claves) | {("edu_ii_2_2_1_total", "INE-2023/departamento/05", "2024")}, {"2024"})
    assert not [f for f in r.controles.fallas if f["control"].startswith("AC-E21")]


def test_ac_e22_y_e24_en_una_corrida_sin_cambios(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    correr(crudo, salida)  # sin cambios: el reporte igual trae controles, cuadros y últimos valores
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert "Sin capturas nuevas" in reporte and "### Controles (AC-E17…AC-E22)" in reporte and "### Últimos valores" in reporte
    assert re.search(r"AC-E22, advertencia\): \d+ \(en \d+ indicadores\)", reporte)
    assert re.search(r"^- `edu_[^`]+`, [^,]+, 2023 → 2024: ", reporte, re.M)
    assert "Faltantes: 0." in reporte


def test_196_el_total_de_ii_3_2_10_2024_no_se_carga_y_el_control_lo_atrapa_si_vuelve():
    """#196: en el archivo 2024 el TOTAL repite «Articulación». Se omite (mantenedor); si un anuario lo vuelve a
    publicar así, AC-E19 (total = suma de los tipos de curso, `desgloses_extra`) frena la carga."""
    import copy

    import mec_anuario as mec
    import mec_anuario_controles as mc

    e = FUENTE["cuadros"]["II-3.2.10"]
    assert all("Articulación" in x["omitir"] for x in e["mapeo"][2024] if x["col"] in "BCDE")
    c = mec.parsear_cuadro(fix(2024), "II-3.2.10", 2024, e["mapeo"][2024], e["tipos"][2024])
    assert not c.datos.indicador.str.startswith("edu_ii_3_2_10_rendimiento_promovido").any()
    manual = yaml.safe_load((RAIZ / "fuentes" / "mec_anuario" / "mapeo_manual.yml").read_text(encoding="utf-8"))
    ok = mc.controles(c.datos, {"cuadros": {"II-3.2.10": e}}, manual, set(), set(c.sin_dato_claves), {"2024"})
    assert not [f for f in ok.controles.fallas if f["control"].startswith("AC-E19")]
    sin_omitir = copy.deepcopy(e)
    for x in sin_omitir["mapeo"][2024]:
        x.pop("omitir", None)
    c2 = mec.parsear_cuadro(fix(2024), "II-3.2.10", 2024, sin_omitir["mapeo"][2024], e["tipos"][2024])
    r = mc.controles(c2.datos, {"cuadros": {"II-3.2.10": sin_omitir}}, manual, set(), set(c2.sin_dato_claves), {"2024"})
    assert any(f["control"].startswith("AC-E19") and "II-3.2.10" in f["detalle"] for f in r.controles.fallas)
