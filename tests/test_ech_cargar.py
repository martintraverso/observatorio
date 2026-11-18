"""F2.5c (#58): carga de la ECH junto al Censo en las mismas tablas (AC-L4, AC-P5, AC-P8, SYSTEM.md §4).

Sobre una copia de la salida del Censo (fixture o completa) y capturas armadas con los tres informes de F2.1.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import ech_cargar
import pandas as pd
import pytest
from ech_captura import capturar, leer_registro
from ech_descubrimiento import Informe

from comun.periodos import trimestre_movil

FIX = Path(__file__).resolve().parent / "fixtures" / "ech_mt"
W = "https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/HTML/ECH/"
PUB = "https://www.gub.uy/instituto-nacional-estadistica/comunicacion/publicaciones/mt-ech-"
URLS = {(2022, 2): W + "Empleo/Mercado%20Laboral%20-%20feb%202022.html",
        (2024, 9): W + "2024/Informe_departamental-Julio-Setiembre2024.html",
        (2026, 9): W + "2026/Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.html"}
ARCHIVOS = {(2022, 2): "ech_mt_2022_02.html", (2024, 9): "ech_mt_2024_09.html", (2026, 9): "ech_mt_2026_09.html"}
ECH = "ine_ech_mercado_trabajo_departamental"
CENSO = "ine_unidades_geoestadisticas_2023"


def informes(urls=URLS):
    return [Informe(trimestre_movil(*fin), PUB + f"{fin[0]}-{fin[1]}", url) for fin, url in urls.items()]


def bajar_de(contenidos):
    return lambda url: contenidos[url]


CONTENIDOS = {url: (FIX / ARCHIVOS[fin]).read_bytes() for fin, url in URLS.items()}


def completar_departamentos(salida: Path) -> None:
    """El fixture del Censo trae 4 departamentos; la ECH publica los 19. En la copia se agregan los que faltan
    (con la geometría de otro: solo importa que el territorio exista). Con los datos completos no cambia nada."""
    import geopandas as gpd

    t = gpd.read_parquet(salida / "territorios.parquet")
    faltan = sorted({f"{i:02d}" for i in range(1, 20)} - set(t[t.nivel == "departamento"].codigo))
    if faltan:
        molde = t[t.nivel == "departamento"].iloc[[0] * len(faltan)].copy()
        molde["codigo"] = faltan
        molde["depto"] = faltan
        molde["id"] = [f"INE-2023/departamento/{c}" for c in faltan]
        gpd.GeoDataFrame(pd.concat([t, molde], ignore_index=True), crs=t.crs).to_parquet(salida / "territorios.parquet")


@pytest.fixture
def entorno(salida, tmp_path):
    """(crudo, salida): copia de la salida del Censo y los tres informes capturados."""
    copia = tmp_path / "salida"
    # Solo las tablas: la web y las descargas (cientos de MB con los datos completos) no hacen falta.
    shutil.copytree(salida, copia, ignore=shutil.ignore_patterns("web", "descargas", "*.pmtiles"))
    completar_departamentos(copia)
    crudo = tmp_path / "crudo"
    capturar(informes(), crudo, bajar_de(CONTENIDOS), hoy="2026-11-18")
    return crudo, copia


def correr(crudo, salida, *extra):
    assert ech_cargar.main([str(crudo / "ech_mt"), "--salida", str(salida), *extra]) == 0


def test_la_ech_se_carga_junto_al_censo_sin_cambiarlo(entorno):
    crudo, salida = entorno
    antes = pd.read_parquet(salida / "observaciones.parquet")
    cap_antes = pd.read_parquet(salida / "capturas.parquet")
    antes = antes[antes.captura_id.isin(cap_antes[cap_antes.fuente_id == CENSO].id)]  # con datos completos ya hay ECH
    correr(crudo, salida)
    obs = pd.read_parquet(salida / "observaciones.parquet")
    cap = pd.read_parquet(salida / "capturas.parquet").set_index("id")
    de = obs.captura_id.map(cap.fuente_id)
    censo = obs[de == CENSO].reset_index(drop=True)
    pd.testing.assert_frame_equal(censo, antes[censo.columns].reset_index(drop=True))  # el Censo no cambia
    ech = obs[de == ECH]
    assert len(ech) == (19 + 8) * 7 * 3 + 7  # tres informes; «Total país» solo en 2026
    assert ech.captura_id.notna().all() and set(ech.captura_id) <= set(cap.index)
    assert set(ech.periodo) == {"2021-12/2022-02", "2024-07/2024-09", "2026-07/2026-09"}
    assert set(ech.tipo_periodo) == {"trimestre_movil"}
    ind = pd.read_parquet(salida / "indicadores.parquet")
    assert set(ind[ind.fuente_id == ECH].tema) == {"Trabajo"} and (ind.fuente_id == ECH).sum() == 7
    caps = cap[cap.fuente_id == ECH]
    assert caps.vigente.all() and set(caps.url) == set(URLS.values()) and set(caps.descargado) == {"2026-11-18"}


def test_cada_valor_en_el_nivel_que_publica_el_ine(entorno):
    crudo, salida = entorno
    correr(crudo, salida)
    con = duckdb.connect(str(salida / "observatorio.duckdb"), read_only=True)
    filas = dict(con.execute("""select nivel || ' ' || periodo, count(*) from v_observaciones
                                where fuente_id = ? group by all""", [ECH]).fetchall())
    assert filas["pais 2026-07/2026-09"] == 7
    assert "pais 2024-07/2024-09" not in filas and "pais 2021-12/2022-02" not in filas  # no se deriva sumando
    assert {k.split()[0] for k in filas} == {"pais", "departamento", "municipio_mvd"}
    assert con.execute("""select valor from v_observaciones where fuente_id = ? and indicador = 'tasa_desempleo'
                          and territorio_id = 'INE-2023/departamento/19' and periodo = '2026-07/2026-09'""",
                       [ECH]).fetchone() == (10.2,)


# AC-L4 (AC-P8)
def test_sin_cambios_no_se_vuelve_a_parsear(entorno, monkeypatch, capsys):
    crudo, salida = entorno
    correr(crudo, salida)
    antes = pd.read_parquet(salida / "observaciones.parquet")

    def no(*a, **k):
        raise AssertionError("no tenía que parsear")

    monkeypatch.setattr(ech_cargar, "parsear_informe", no)
    capsys.readouterr()
    correr(crudo, salida)
    assert '"resultado": "sin cambios"' in capsys.readouterr().out
    pd.testing.assert_frame_equal(pd.read_parquet(salida / "observaciones.parquet"), antes)
    hist = pd.read_parquet(salida / "capturas_historial.parquet")
    assert hist[hist.fuente_id == ECH].resultado.tolist()[-1] == "sin cambios"


def test_una_captura_nueva_solo_parsea_esa(entorno, monkeypatch, capsys):
    crudo, salida = entorno
    correr(crudo, salida)
    v11 = URLS[(2026, 9)].replace("v1_0", "v1_1")
    capturar(informes({**URLS, (2026, 9): v11}), crudo,
             bajar_de({**CONTENIDOS, v11: CONTENIDOS[URLS[(2026, 9)]].replace(b"64,1", b"64,2", 1)}), hoy="2026-12-01")
    parseados = []
    original = ech_cargar.parsear_informe
    monkeypatch.setattr(ech_cargar, "parsear_informe", lambda h, archivo=None: parseados.append(archivo) or original(h, archivo))
    correr(crudo, salida)
    assert parseados == ["Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_1.html"]
    obs = pd.read_parquet(salida / "observaciones.parquet")
    cap = pd.read_parquet(salida / "capturas.parquet").set_index("id")
    vieja, nueva = (c["id"] for c in leer_registro(crudo) if c["periodo"] == "2026-07/2026-09")
    assert not cap.loc[vieja].vigente and cap.loc[nueva].vigente  # la anterior queda trazable
    assert vieja not in set(obs.captura_id)  # pero solo la vigente da valores
    pais = obs[(obs.territorio_id == "INE-2023/pais/UY") & (obs.indicador == "tasa_actividad")]
    assert pais.valor.tolist() == [64.2] and not obs.duplicated(["indicador", "territorio_id", "periodo"]).any()


def test_reprocesar_el_censo_no_pierde_la_ech(entorno):
    """Como en Actions: si la carpeta de una fuente falta, se reconstruye desde las tablas compartidas."""
    crudo, salida = entorno
    correr(crudo, salida)
    n = len(pd.read_parquet(salida / "observaciones.parquet"))
    shutil.rmtree(salida / "fuentes")
    from comun.registro import RAIZ, cargar_fuentes
    from comun.salida import combinar

    combinar(salida, cargar_fuentes(RAIZ / "fuentes"))
    assert len(pd.read_parquet(salida / "observaciones.parquet")) == n
    assert sorted(p.name for p in (salida / "fuentes").iterdir()) == sorted([CENSO, ECH])


def test_las_tablas_tienen_que_encajar(entorno):
    from comun.registro import RAIZ, cargar_fuentes
    from comun.salida import ErrorCombinar, combinar

    crudo, salida = entorno
    correr(crudo, salida)
    d = salida / "fuentes" / ECH
    obs = pd.read_parquet(d / "observaciones.parquet")
    obs.loc[0, "territorio_id"] = "INE-2023/departamento/99"
    obs.to_parquet(d / "observaciones.parquet", index=False)
    with pytest.raises(ErrorCombinar, match="sin territorio"):
        combinar(salida, cargar_fuentes(RAIZ / "fuentes"))


def test_las_advertencias_quedan_en_el_historial_y_en_el_reporte(entorno):
    crudo, salida = entorno
    import json

    from ech_captura import leer_registro

    c = [x for x in leer_registro(crudo) if x["periodo"] == "2026-07/2026-09"][0]
    path = crudo / c["archivo"]
    from test_ech_parser import cambiar_celda

    nuevo = cambiar_celda(path.read_text(encoding="utf-8"), "65,5", "65,4", desde="Total Montevideo").encode()
    path.write_bytes(nuevo)  # simula un informe del INE con la diferencia de redondeo
    import hashlib

    reg = json.loads((crudo / "ech_mt" / "capturas.json").read_text(encoding="utf-8"))
    for x in reg["capturas"]:
        if x["id"] == c["id"]:
            x["sha256"] = hashlib.sha256(nuevo).hexdigest()
            x["id"] = f"{ECH}:{x['sha256'][:12]}"
    (crudo / "ech_mt" / "capturas.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    correr(crudo, salida)
    hist = pd.read_parquet(salida / "capturas_historial.parquet")
    assert hist.detalle.str.contains("Total Montevideo» tasa_actividad: 65,4").sum() == 1
    reporte = (salida / "reporte_validacion.md").read_text(encoding="utf-8")
    assert "## Mercado de trabajo (ECH): advertencias" in reporte and "65,4 en los cuadros de municipios" in reporte
    correr(crudo, salida)  # sin cambios: la advertencia sigue en el reporte (sale del historial)
    assert (salida / "reporte_validacion.md").read_text(encoding="utf-8").count("65,4 en los cuadros") == 1


def no_parsear(*a, **k):
    raise AssertionError("no tenía que parsear")


def test_en_un_runner_limpio_tambien_da_sin_cambios(entorno, monkeypatch, capsys):
    """En Actions se baja solo lo compartido: sin carpetas de fuentes, igual no se vuelve a parsear."""
    crudo, salida = entorno
    correr(crudo, salida)
    shutil.rmtree(salida / "fuentes")
    monkeypatch.setattr(ech_cargar, "parsear_informe", no_parsear)
    capsys.readouterr()
    correr(crudo, salida)
    assert '"resultado": "sin cambios"' in capsys.readouterr().out


def test_si_combinar_falla_la_corrida_siguiente_vuelve_a_intentar(entorno, capsys):
    import geopandas as gpd

    crudo, salida = entorno
    territorios = gpd.read_parquet(salida / "territorios.parquet")
    territorios[territorios.id != "INE-2023/departamento/19"].to_parquet(salida / "territorios.parquet")
    carpeta = salida / "fuentes" / ECH
    antes = {f.name: f.read_bytes() for f in carpeta.glob("*")} if carpeta.exists() else None
    previas = len(pd.read_parquet(salida / "capturas_historial.parquet")) if (
        salida / "capturas_historial.parquet").exists() else 0
    with pytest.raises(Exception, match="sin territorio"):
        ech_cargar.main([str(crudo / "ech_mt"), "--salida", str(salida)])
    hist = pd.read_parquet(salida / "capturas_historial.parquet").iloc[previas:]
    assert hist[hist.fuente_id == ECH].resultado.tolist() == ["error"]
    # no quedó una carpeta sin publicar: o no existe, o es la de antes (con datos completos ya había ECH)
    assert (not carpeta.exists()) if antes is None else {f.name: f.read_bytes() for f in carpeta.glob("*")} == antes
    territorios.to_parquet(salida / "territorios.parquet")
    capsys.readouterr()
    correr(crudo, salida)
    assert '"resultado": "nuevo"' in capsys.readouterr().out
    cap = pd.read_parquet(salida / "capturas.parquet")
    assert set(cap[cap.fuente_id == ECH].url) == set(URLS.values())


def test_una_captura_que_vuelve_a_ser_vigente_se_parsea(entorno):
    import json

    crudo, salida = entorno
    path = crudo / "ech_mt" / "capturas.json"
    reg = json.loads(path.read_text(encoding="utf-8"))
    reg["capturas"][0]["vigente"] = False  # 2022-02
    path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    correr(crudo, salida)
    assert "2021-12/2022-02" not in set(pd.read_parquet(salida / "observaciones.parquet").periodo)
    reg["capturas"][0]["vigente"] = True
    path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    correr(crudo, salida)
    obs = pd.read_parquet(salida / "observaciones.parquet")
    assert (obs.periodo == "2021-12/2022-02").sum() == (19 + 8) * 7
