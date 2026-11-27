"""F4.6 (#169, AC-E25): novedades de los anuarios del MEC, sin red ni GitHub (página, descarga y `gh` falsos)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

from mec_anuario_novedades import (
    CARPETA,
    PAGINA,
    PAGINA_ANIO,
    anios_en_pagina,
    novedades,
    titulo_actualizado,
    titulo_issue,
)

BASE = "https://www.gub.uy/ministerio-educacion-cultura/sites/ministerio-educacion-cultura/files/"
URL = {a: f"{BASE}2026-01/Anuario%20{a}.xlsx" for a in range(2020, 2026)}
REGISTRADOS = range(2020, 2025)
LISTADO = "".join(f'<a href="/ministerio-educacion-cultura/datos-y-estadisticas/datos/anuario-estadistico-educacion-{a}">{a}</a>'
                  for a in (2015, 2019, *range(2020, 2026)))
FUENTE = {"anuarios": {a: {"url": URL[a]} for a in REGISTRADOS}}


def xlsx(texto: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("xl/workbook.xml", texto)
    return b.getvalue()


def pedir_con(urls: dict[int, str]):
    def pedir(url: str) -> bytes:
        if url == PAGINA:
            return LISTADO.encode()
        for a, u in urls.items():
            if url == PAGINA_ANIO.format(anio=a):
                return f'<a href="{u}">Descargar</a>'.encode()
        raise AssertionError(f"no se pide {url}")
    return pedir


def bajar(url: str) -> bytes:
    assert url == URL[2025], url
    return xlsx("anuario 2025")


class Gh:
    """`gh` falso: recuerda los issues creados y los devuelve en `issue list`."""

    def __init__(self):
        self.titulos: list[str] = []

    def __call__(self, *args: str) -> str:
        if args[:2] == ("issue", "list"):
            return json.dumps([{"title": t} for t in self.titulos])
        if args[:2] == ("issue", "create"):
            self.titulos.append(args[args.index("--title") + 1])
            assert "necesita-humano" in args
            return "https://github.com/x/y/issues/1"
        raise AssertionError(args)


def test_ac_e25_lee_los_anios_de_la_pagina():
    assert anios_en_pagina(LISTADO) == [2015, 2019, 2020, 2021, 2022, 2023, 2024, 2025]


def test_ac_e25_un_anio_nuevo_se_baja_sin_cargarlo_y_abre_un_issue_una_sola_vez(tmp_path):
    gh = Gh()
    r = novedades(tmp_path, FUENTE, pedir=pedir_con(URL), gh=gh, bajar=bajar)
    # 2015 y 2019 (anteriores al registro, en .rar: F4.9) no son nuevos ni se piden; los del registro no cambiaron
    assert r["nuevos"] == [2025] and r["actualizados"] == [] and r["issues"] == [2025] and r["errores"] == {}
    nuevo = tmp_path / CARPETA / "nuevos" / "2025.xlsx"
    assert nuevo.read_bytes() == xlsx("anuario 2025")  # el original sin cambios
    anotado = json.loads((tmp_path / CARPETA / "nuevos" / "nuevos.json").read_text())["2025"]
    assert anotado["sha256"] == hashlib.sha256(xlsx("anuario 2025")).hexdigest() and anotado["url"] == URL[2025]
    # no se carga: no entra en el registro de capturas que lee la carga
    assert not (tmp_path / CARPETA / "capturas.json").exists()
    # la corrida siguiente no repite el issue
    r2 = novedades(tmp_path, FUENTE, pedir=pedir_con(URL), gh=gh, bajar=bajar)
    assert r2["nuevos"] == [2025] and r2["issues"] == [] and gh.titulos == [titulo_issue(2025)]


def test_ac_e25_un_anuario_del_registro_con_otra_url_en_su_pagina_avisa_una_sola_vez(tmp_path):
    """El MEC volvió a subir 2024 en otra carpeta: la página enlaza otro xlsx que el del registro."""
    urls = {**{a: URL[a] for a in REGISTRADOS}, 2024: f"{BASE}2026-02/Anuario%202024_0.xlsx"}
    fuente_sin_2025 = FUENTE
    listado = LISTADO.replace("anuario-estadistico-educacion-2025", "otra-cosa")
    pedir = pedir_con(urls)

    def pedir_sin_2025(url: str) -> bytes:
        return listado.encode() if url == PAGINA else pedir(url)

    gh = Gh()
    r = novedades(tmp_path, fuente_sin_2025, pedir=pedir_sin_2025, gh=gh, bajar=bajar)
    assert r["actualizados"] == [2024] and r["nuevos"] == [] and gh.titulos == [titulo_actualizado(2024)]
    r2 = novedades(tmp_path, fuente_sin_2025, pedir=pedir_sin_2025, gh=gh, bajar=bajar)
    assert r2["actualizados"] == [2024] and r2["issues"] == [] and len(gh.titulos) == 1


def test_ac_e25_sin_anios_nuevos_no_baja_nada(tmp_path):
    fuente = {"anuarios": {a: {"url": URL[a]} for a in range(2020, 2026)}}
    r = novedades(tmp_path, fuente, pedir=pedir_con(URL), gh=Gh(), bajar=bajar)
    assert r["nuevos"] == [] and r["actualizados"] == [] and not (tmp_path / CARPETA / "nuevos").exists()


def test_ac_e25_lo_que_no_es_un_xlsx_no_se_guarda_y_no_frena_la_corrida(tmp_path):
    gh = Gh()
    r = novedades(tmp_path, FUENTE, pedir=pedir_con(URL), gh=gh, bajar=lambda url: b"<html>error</html>")
    assert r["nuevos"] == [] and "no es un xlsx" in r["errores"]["2025"] and gh.titulos == []
    assert not (tmp_path / CARPETA / "nuevos" / "2025.xlsx").exists()
