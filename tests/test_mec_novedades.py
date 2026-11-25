"""F4.6 (#169, AC-E25): novedades de los anuarios del MEC, sin red ni GitHub (página y `gh` falsos)."""

from __future__ import annotations

import hashlib
import json

from mec_anuario_novedades import CARPETA, PAGINA, PAGINA_ANIO, anios_en_pagina, novedades, titulo_issue

XLSX_2025 = "https://www.gub.uy/ministerio-educacion-cultura/sites/ministerio-educacion-cultura/files/2027-01/Anuario%202025.xlsx"
LISTADO = "".join(f'<a href="/ministerio-educacion-cultura/datos-y-estadisticas/datos/anuario-estadistico-educacion-{a}">{a}</a>'
                  for a in (2015, 2019, 2020, 2021, 2022, 2023, 2024, 2025))
FUENTE = {"anuarios": {a: {"url": "x"} for a in (2020, 2021, 2022, 2023, 2024)}}


def pedir(url: str) -> bytes:
    if url == PAGINA:
        return LISTADO.encode()
    if url == PAGINA_ANIO.format(anio=2025):
        return f'<a href="{XLSX_2025}">Descargar</a>'.encode()
    if url == XLSX_2025:
        return b"contenido del anuario 2025"
    raise AssertionError(f"no se pide {url}")


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
    r = novedades(tmp_path, FUENTE, pedir=pedir, gh=gh)
    # 2015 y 2019 (anteriores al registro, en .rar: F4.9) no son nuevos ni se piden
    assert r["nuevos"] == [2025] and r["issues"] == [2025] and r["errores"] == {}
    nuevo = tmp_path / CARPETA / "nuevos" / "2025.xlsx"
    assert nuevo.read_bytes() == b"contenido del anuario 2025"  # el original sin cambios
    anotado = json.loads((tmp_path / CARPETA / "nuevos" / "nuevos.json").read_text())["2025"]
    assert anotado["sha256"] == hashlib.sha256(b"contenido del anuario 2025").hexdigest() and anotado["url"] == XLSX_2025
    # no se carga: no entra en el registro de capturas que lee la carga
    assert not (tmp_path / CARPETA / "capturas.json").exists()
    # la corrida siguiente no repite el issue
    r2 = novedades(tmp_path, FUENTE, pedir=pedir, gh=gh)
    assert r2["nuevos"] == [2025] and r2["issues"] == [] and gh.titulos == [titulo_issue(2025)]


def test_ac_e25_sin_anios_nuevos_no_baja_nada(tmp_path):
    fuente = {"anuarios": {a: {} for a in range(2020, 2026)}}
    r = novedades(tmp_path, fuente, pedir=pedir, gh=Gh())
    assert r["nuevos"] == [] and not (tmp_path / CARPETA / "nuevos").exists()


def test_ac_e25_un_anio_que_falla_no_frena_la_corrida(tmp_path):
    def pedir_roto(url: str) -> bytes:
        if url == XLSX_2025:
            raise OSError("sin respuesta")
        return pedir(url)

    r = novedades(tmp_path, FUENTE, pedir=pedir_roto, gh=Gh())
    assert r["nuevos"] == [] and "2025" in r["errores"]
