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
        assert f["http"] == 200, a


def test_ac_e2_cada_cuadro_tiene_tipo_ola_y_mapeo_en_la_ola_1():
    assert len([c for c, e in REG["cuadros"].items() if 2024 in e["anios"]]) == 110
    assert len([c for c, e in REG["cuadros"].items() if 2023 in e["anios"]]) == 107
    for cod, e in REG["cuadros"].items():
        assert set(e["tipos"]) == set(e["anios"]), cod
        assert set(e["tipos"].values()) <= {"A", "B", "C", None}, cod
        assert e["ola"] in (1, 2), cod
        if e["ola"] == 1:
            assert set(e["mapeo"]) == set(e["anios"]), cod
            for a, m in e["mapeo"].items():
                if m is None:  # lo que no se carga figura con motivo
                    assert e["sin_cargar"][a], (cod, a)
                else:  # cada columna, su propio indicador
                    assert len({e["col"] for e in m}) == len(m), (cod, a)
                    assert len({e["id"] for e in m}) == len(m), (cod, a)


def ruta_id(cod, anio):
    return {e["ruta"]: e["id"] for e in REG["cuadros"][cod]["mapeo"][anio] if not e.get("repetida")}


def test_ii_2_1_4_total_y_total_comun_son_indicadores_distintos():
    m = REG["cuadros"]["II-2.1.4"]["mapeo"][2024]
    assert m[0]["id"] == "edu_ii_2_1_4_total" and len({e["id"] for e in m}) == len(m)


def test_ii_4_2_4_las_tres_columnas_varon_son_total_publica_y_privada():
    m = REG["cuadros"]["II-4.2.4"]["mapeo"][2024]
    varon = [e for e in m if e["ruta"] == "SEXO/Varón"]
    assert [e["concepto"] for e in varon] == ["TOTAL/SEXO/Varón", "PÚBLICA/SEXO/Varón", "PRIVADA/SEXO/Varón"]
    assert len({e["id"] for e in varon}) == 3 and all(not e.get("repetida") for e in varon)


def test_ii_1_2_2_las_edades_son_parte_de_la_ruta():
    rutas = [e["ruta"] for e in REG["cuadros"]["II-1.2.2"]["mapeo"][2024]]
    assert any(r.endswith("/AÑOS/3") for r in rutas) and any(r.endswith("/AÑOS/6") for r in rutas)


def test_ii_1_1_1_2020_jardines_quedan_bajo_publica_como_en_2024():
    m20, m24 = (set(ruta_id("II-1.1.1", a)) for a in (2020, 2024))
    assert "FORMA DE ADMINISTRACIÓN/PÚBLICA/Jardines de Tiempo Completo" in m20 & m24


def test_ii_2_2_1_el_sexo_de_2024_es_otro_indicador_que_el_de_2023():
    m23, m24 = ruta_id("II-2.2.1", 2023), ruta_id("II-2.2.1", 2024)
    ruta = "FORMA DE ADMINISTRACIÓN/TOTAL/MUJER"
    assert m23[ruta] != m24[ruta]
    assert m23["TOTAL"] == m24["TOTAL"]


def test_fixtures_tienen_la_ola_1_la_serie_y_cuadros_b_y_c():
    ola1 = {c for c, e in REG["cuadros"].items() if e["ola"] == 1}
    for anio in (2024, 2023):
        h = hojas(FIXTURES / f"{anio}.xlsx")
        presentes = {c for c in ola1 if anio in REG["cuadros"][c]["anios"]}
        assert presentes <= h, presentes - h
        assert any(x.startswith("MATRÍCULA DEL SISTEMA") for x in h)
        tipos = [REG["cuadros"][c]["tipos"][anio] for c in h if c in REG["cuadros"]]
        assert tipos.count("B") >= 2 and tipos.count("C") >= 2


def test_ii_2_2_13_el_total_vacio_es_de_no_promovidos():
    m = ruta_id("II-2.2.13", 2024)
    assert "RENDIMIENTO ESCOLAR/NO PROMOVIDOS/TOTAL" in m
    assert not any(r.startswith("RENDIMIENTO ESCOLAR/PROMOVIDOS/TOTAL") and r != "RENDIMIENTO ESCOLAR/PROMOVIDOS/TOTAL" for r in m)


def test_ii_2_2_1_2024_el_total_por_sexo_solo_publica_no_se_carga():
    m = {e["ruta"]: e for e in REG["cuadros"]["II-2.2.1"]["mapeo"][2024]}
    assert "PÚBLICA" in m["FORMA DE ADMINISTRACIÓN/TOTAL/MUJER"]["omitir"]
    assert "omitir" not in m["FORMA DE ADMINISTRACIÓN/PÚBLICA/SEXO/M"]
    assert not any("omitir" in e for e in REG["cuadros"]["II-2.2.1"]["mapeo"][2023])


# ---------------------------------------------------------------- F4.3b-1 (#182): mapeo a mano (D4, D5)

def mec_plegar(t):
    import mec_anuario

    return mec_anuario.plegar(t)


def test_d4_ii_1_1_2_2021_cpip_se_compara_con_su_par_de_2020_y_queda_en_2021():
    c = next(x for x in REG["cuadros"]["II-1.1.2"]["mapeo"][2021] if "CPIP" in x["ruta"])
    assert "anio" not in c and not c.get("omitir")
    assert "difiere del anuario 2020" in " ".join(REG["cuadros"]["II-1.1.2"]["anio_real_notas"][2021])


def entradas_ola_1():
    for cod, e in REG["cuadros"].items():
        if e["ola"] != 1:
            continue
        for anio, m in e["mapeo"].items():
            for x in m or []:
                yield cod, anio, x


def test_d5_ninguna_columna_de_la_ola_1_queda_repetida():
    assert [(c, a, x["col"]) for c, a, x in entradas_ola_1() if x.get("repetida")] == []
    assert not any(e.get("mapeo_manual_fallas") for e in REG["cuadros"].values())


def test_d5_cada_mapeo_a_mano_tiene_su_comprobacion():
    hechos = [(c, a, x) for c, a, x in entradas_ola_1() if "concepto" in x]
    assert len(hechos) >= 60
    assert all(x["comprobado"] for _, _, x in hechos)


def test_d5_las_sumas_cierran_en_los_fixtures():
    """Cada «X = A + B …» del registro se vuelve a calcular sobre los fixtures 2024 y 2023, fila por fila, con el
    lector del pipeline."""
    import mec_anuario as mec

    probadas = 0
    for anio in (2024, 2023):
        xlsx = (FIXTURES / f"{anio}.xlsx").read_bytes()
        hojas = {h.strip(): h for h in mec.nombres_de_hojas(xlsx)}
        for cod, a, x in entradas_ola_1():
            prueba = x.get("comprobado", "")
            m = re.fullmatch(r"([A-Z]+) = ([A-Z]+(?: \+ [A-Z]+)*)", prueba)
            if a != anio or not m or cod not in hojas:
                continue
            celdas, combinadas = mec.celdas_de(xlsx, hojas[cod])
            e = mec.estructura(celdas, combinadas, cod)
            total, partes = mec._col(m.group(1)), [mec._col(p) for p in m.group(2).split(" + ")]
            for fila, _ in e.filas:
                t = mec.numero(celdas.get((fila, total)))
                if t is not None:
                    assert t == sum(mec.numero(celdas.get((fila, p))) or 0 for p in partes), (cod, anio, prueba, fila)
            probadas += 1
    assert probadas >= 20


def test_d4_columnas_de_otro_anio():
    reglas = yaml.safe_load((RAIZ / "fuentes" / "mec_anuario" / "mapeo_manual.yml").read_text(encoding="utf-8"))["anio_real"]
    for cod, por_anio in reglas.items():
        for anio, regla in por_anio.items():
            m = REG["cuadros"][cod]["mapeo"][anio]
            if m is None:  # el cuadro-año no se carga (II-2.1.4 2021: el título dice 2020)
                assert REG["cuadros"][cod]["sin_cargar"][anio]
                continue
            notas = (REG["cuadros"][cod].get("anio_real_notas") or {}).get(anio, [])
            filtro = regla["columnas"]
            alcanzadas = [x for x in m if filtro == "todas" or filtro in mec_plegar(x["ruta"])]
            assert alcanzadas, (cod, anio)
            for x in alcanzadas:  # cada columna que declara el pie: año real, omitida o anotada con el motivo
                assert x.get("anio") == regla["anio"] or "D4" in (x.get("omitir") or "") or any(n.startswith(f"{x['col']} «") for n in notas), (cod, anio, x["col"])


def test_d4_ningun_valor_queda_dos_veces_en_el_mismo_anio():
    vistos = {}
    for cod, a, x in entradas_ola_1():
        if x.get("omitir"):
            continue
        clave = (x["id"], x.get("anio", a))
        assert clave not in vistos, (clave, vistos.get(clave), (cod, a))
        vistos[clave] = (cod, a)


def test_d4_lo_que_ya_publica_su_anuario_no_se_vuelve_a_cargar():
    m = {x["ruta"]: x for x in REG["cuadros"]["II-2.2.1"]["mapeo"][2021]}
    privada = [x for r, x in m.items() if "PRIVADA" in r.upper()]
    assert privada and all("ya cargado desde el anuario 2020" in x["omitir"] for x in privada)


# ---------------------------------------------------------------- F4.3b-2 (#183): conceptos según 2024 (D6)

def test_d6_cada_id_de_2020_a_2023_esta_en_2024_o_tiene_motivo():
    sin = []
    for cod, e in REG["cuadros"].items():
        if e["ola"] != 1 or not e["mapeo"].get(2024):
            continue
        ids24 = {x["id"] for x in e["mapeo"][2024]}
        for anio in (2020, 2021, 2022, 2023):
            for x in e["mapeo"].get(anio) or []:
                if not x.get("omitir") and x["id"] not in ids24 and not x.get("motivo_d6"):
                    sin.append((cod, anio, x["col"]))
    assert sin == []


def test_d6_un_curso_solo_publico_en_2024_usa_el_id_de_2024():
    m22 = {x["ruta"]: x for x in REG["cuadros"]["II-4.2.2"]["mapeo"][2022]}
    m24 = {x["ruta"]: x for x in REG["cuadros"]["II-4.2.2"]["mapeo"][2024]}
    assert m22["BACHILLERATO PROFESIONAL/Sexo/M"]["id"] == m24["PÚBLICA/BACHILLERATO PROFESIONAL/Sexo/M"]["id"]
    assert "PÚBLICA" in m22["BACHILLERATO PROFESIONAL/Sexo/M"]["equivale_2024"]


def test_d6_lo_que_2024_agrupa_conserva_su_id_y_no_se_suma():
    ids24 = {x["id"] for x in REG["cuadros"]["II-1.2.2"]["mapeo"][2024]}
    comun = [x for x in REG["cuadros"]["II-1.2.2"]["mapeo"][2022] if "JARDÍN COMÚN" in x["ruta"]]
    assert comun and all(x["id"] not in ids24 and "JARDÍN DE INFANTES" in x["motivo_d6"] for x in comun)


def test_d6_ac_e13_el_sexo_de_ii_2_2_1_2023_no_usa_un_id_de_2024():
    m23 = {x["ruta"]: x for x in REG["cuadros"]["II-2.2.1"]["mapeo"][2023]}
    x = m23["FORMA DE ADMINISTRACIÓN/TOTAL/VARÓN"]
    assert "equivale_2024" not in x and x["motivo_d6"]
