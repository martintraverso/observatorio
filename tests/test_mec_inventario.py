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


def test_registro_valida_y_queda_activa():
    assert validar_fuente(REG, "mec_anuario_educacion.yml") == []
    assert REG["estado"] == "activa"  # F4.10 (#222): la app publica la educación


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
    assert "equivale_2024" not in x and "AC-E13" in x["motivo_d6"]


def motivo(cod, anio, ruta):
    x = next(x for x in REG["cuadros"][cod]["mapeo"][anio] if x["ruta"] == ruta)
    return x.get("equivale_2024"), x.get("motivo_d6", "")


def test_d6_un_curso_con_parte_privada_en_2023_no_se_une_a_la_publica_de_2024():
    """II-4.2.2: la EMP de 2022 no separa administración y en 2023 tiene parte privada (Don Bosco)."""
    eq, mot = motivo("II-4.2.2", 2022, "EDUCACIÓN MEDIA PROFESIONAL/TOTAL")
    assert eq is None and "AC-E13" in mot


def test_d6_un_total_sin_privados_no_se_une_al_que_los_incluye():
    """II-3.1.1: hasta 2022 «TOTAL ESCUELAS DE CBT Y TÉCNICA» es solo pública; desde 2023 suma privados."""
    ruta = next(x["ruta"] for x in REG["cuadros"]["II-3.1.1"]["mapeo"][2022] if "TOTAL ESCUELAS" in x["ruta"])
    eq, mot = motivo("II-3.1.1", 2022, ruta)
    assert eq is None and "no incluye privados" in mot


def test_d6_desempata_por_la_ruta_mas_parecida():
    """II-3.1.1 2023: «TOTAL PÚBLICOS» de la DGETP va al de la DGETP de 2024, no al total público general."""
    m23 = REG["cuadros"]["II-3.1.1"]["mapeo"][2023]
    m24 = {x["ruta"]: x["id"] for x in REG["cuadros"]["II-3.1.1"]["mapeo"][2024]}
    o = next(x for x in m23 if x["col"] == "O")
    assert o["id"] == m24["MODALIDAD/DGETP/FORMA DE ADMINISTRACIÓN/TOTAL PÚBLICOS"]


def test_d6_un_id_que_ya_era_igual_a_2024_tambien_se_separa_si_cambia_la_cobertura():
    """II-3.1.1: el TOTAL GENERAL de 2020–2022 no incluye privados de la DGETP; el de 2024 sí (AC-E13)."""
    i24 = next(x["id"] for x in REG["cuadros"]["II-3.1.1"]["mapeo"][2024] if x["ruta"] == "TOTAL GENERAL")
    i22 = next(x for x in REG["cuadros"]["II-3.1.1"]["mapeo"][2022] if x["ruta"] == "TOTAL GENERAL")
    assert i22["id"] == i24 + "_sin_privados" and "AC-E13" in i22["motivo_d6"]
    # «TOTAL LICEOS PRIVADOS» dice su cobertura: no se separa
    assert not any(x["id"].endswith("_sin_privados") for x in REG["cuadros"]["II-3.1.1"]["mapeo"][2022] if "PRIVADOS" in x["ruta"])


def test_173_ii_6_3_2_el_sexo_m_f_de_2020_a_2022_es_varon_y_mujer():
    """#173: II-6.3.2 rotula el sexo «M/F» en 2020–2022 y «V/M» desde 2023. La «M» de 2020 (masculino) va al id de los
    varones de 2023, no al de las mujeres (AC-E13)."""
    m = {a: {x["col"]: x["id"] for x in REG["cuadros"]["II-6.3.2"]["mapeo"][a]} for a in (2020, 2023)}
    for a in (2020, 2021, 2022):
        rutas = {x["col"]: x["ruta"] for x in REG["cuadros"]["II-6.3.2"]["mapeo"][a]}
        assert rutas["D"].endswith("/SEXO/M") and rutas["E"].endswith("/SEXO/F")
    for col in "DEGHJK":
        assert m[2020][col] == m[2023][col], col
    assert m[2020]["D"].endswith("20_horas_o_menos_sexo_v")


def test_173_ii_6_3_2_2024_repite_2023_y_no_se_vuelve_a_cargar():
    """#173 (D4): el pie de 2024 dice «último dato disponible año 2023» y los valores son los del anuario 2023."""
    assert all(x.get("omitir") for x in REG["cuadros"]["II-6.3.2"]["mapeo"][2024])


def test_173_el_total_de_un_tramo_en_cero_es_un_dato():
    """#173: una columna «Total» repetida en 0 que su grupo prueba (0 = 0 + 0) se carga; antes quedaba como separador
    del encabezado (II-5.3.2 2020: el tramo «Entre 21 y 30 horas»)."""
    m = {x["col"]: x for x in REG["cuadros"]["II-5.3.2"]["mapeo"][2020]}
    assert not m["F"].get("omitir") and m["F"]["id"] == "edu_ii_5_3_2_horas_semanales_entre_21_y_30_horas_total"


def test_241_ii_7_1_los_ids_de_2020_a_2023_son_los_de_2024_salvo_la_matricula_que_cambia():
    """#241: «EGRESADOS» (y en II-7.1.2 «INGRESADOS») de años anteriores son el «EGRESO» de 2024: un id por medida.
    La matrícula cambia de alcance y va con id propio (AC-E13, mantenedor): en grado, el total de 2020–2023 incluye la
    matrícula UdelaR sin sexo (`_con_sin_sexo`); en posgrado, 2020–2022 incluyen a la UdelaR del censo 2012."""
    def ids(cod, a):
        return {x["col"]: x["id"] for x in REG["cuadros"][cod]["mapeo"][a]}
    for a in (2020, 2021, 2022, 2023):
        d = {c: i for c, i in ids("II-7.1.1", a).items() if ids("II-7.1.1", 2024)[c] != i}
        assert d == {"E": "edu_ii_7_1_1_matricula_total_con_sin_sexo"}, (a, d)
    for a in (2020, 2021, 2022):
        d = {c: i for c, i in ids("II-7.1.2", a).items() if ids("II-7.1.2", 2024)[c] != i}
        assert set(d) == {"E", "F", "G"} and all(i.endswith("_con_udelar_censo_2012") for i in d.values()), (a, d)
    assert ids("II-7.1.2", 2023) == ids("II-7.1.2", 2024)
    assert REG["cuadros"]["II-7.1.1"]["tipos"][2024] == "A"


def test_255_ii_7_2_1_a_3_un_id_por_medida_en_los_cinco_anios():
    """#255: «INGRESADOS», «MATRICULADOS» y «EGRESADOS» de 2020–2023 son el «INGRESO», la «MATRÍCULA» y el «EGRESO» de
    2024 (renombres): un id por medida y año. En II-7.2.2 las columnas AB, AE y AF (números sueltos fuera del cuadro)
    llevan `omitir`."""
    for cod in ("II-7.2.1", "II-7.2.2", "II-7.2.3"):
        e = REG["cuadros"][cod]
        assert e["ola"] == 1 and all(t == "C" for t in e["tipos"].values()), cod
        ids = {a: {x["col"]: x["id"] for x in m if not x.get("omitir")} for a, m in e["mapeo"].items()}
        assert all(v == ids[2024] for v in ids.values()), cod
    omitidas = {x["col"] for x in REG["cuadros"]["II-7.2.2"]["mapeo"][2024] if x.get("omitir")}
    assert omitidas == {"AB", "AE", "AF"}
