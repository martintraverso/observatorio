"""Pruebas de la automatización de datos (M3): correr.py, conseguir_originales.py y publicar.py.

Siempre sobre el fixture y con un `gh` falso (tests/gh_falso.py): nada toca GitHub ni la red.
AC-A2 y AC-A3 se verifican a mano en GitHub; acá se prueba la lógica que los sostiene.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml
from conftest import FIXTURES, RAIZ

FUENTE = "ine_unidades_geoestadisticas_2023"
ORIGINAL = "Unidades_Geoestadisticas_Censo_2023.zip"
ARG_FIXTURE = f"{FUENTE}=--esperado {FIXTURES / 'esperado.yml'}"


@pytest.fixture
def gh(tmp_path, monkeypatch) -> Path:
    """Pone un `gh` falso primero en el PATH; devuelve la carpeta donde guarda los releases."""
    binario = tmp_path / "bin"
    binario.mkdir()
    (binario / "gh").write_text(f"#!/bin/sh\nexec {sys.executable} {RAIZ / 'tests' / 'gh_falso.py'} \"$@\"\n")
    (binario / "gh").chmod((binario / "gh").stat().st_mode | stat.S_IEXEC)
    datos = tmp_path / "github"
    monkeypatch.setenv("PATH", f"{binario}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GH_FALSO_DIR", str(datos))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return datos


def estado(gh: Path) -> dict:
    return json.loads((gh / "estado.json").read_text()) if (gh / "estado.json").exists() else {}


def correr(script: str, *args, env=None):
    r = subprocess.run([sys.executable, str(RAIZ / script), *map(str, args)], capture_output=True, text=True,
                       cwd=RAIZ, env={**os.environ, **(env or {})})
    return r


def solo_censo(carpeta: Path) -> Path:
    """Registro con solo el Censo: estos tests son de la orquestación sobre su fixture (la ECH, que necesita
    los 19 departamentos y sus originales en crudos, se prueba en test_ech_cargar.py y más abajo)."""
    f = carpeta / "fuentes_censo"
    if not f.exists():
        f.mkdir(parents=True)
        shutil.copy(RAIZ / "fuentes" / f"{FUENTE}.yml", f)
    return f


def pipeline(crudo: Path, salida: Path, *extra):
    # Sin PMTiles: acá se prueba la orquestación, no las teselas (eso está en test_web.py).
    r = correr("pipeline/correr.py", "--crudo", crudo, "--salida", salida, "--argumentos", ARG_FIXTURE,
               "--fuentes", solo_censo(crudo.parent), "--sin-pmtiles", *extra)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture
def crudo(tmp_path) -> Path:
    """datos/crudo de prueba: el fixture con el nombre del original real."""
    c = tmp_path / "crudo"
    c.mkdir()
    shutil.copy(FIXTURES / "ine_2023_mini.zip", c / ORIGINAL)
    return c


# ------------------------------------------------------------------ correr.py (un comando reconstruye todo)

def test_correr_procesa_publica_y_despues_dice_sin_cambios(crudo, tmp_path):
    salida = tmp_path / "salida"
    r1 = pipeline(crudo, salida)
    assert r1["fuentes"][FUENTE]["resultado"] == "nuevo"
    assert r1["web"] and r1["publicar"] and r1["errores"] == []
    assert (salida / "web" / "manifest.json").exists()

    r2 = pipeline(crudo, salida)
    assert r2["fuentes"][FUENTE]["resultado"] == "sin cambios"
    assert not r2["web"] and not r2["publicar"]

    r3 = pipeline(crudo, salida, "--forzar")
    assert r3["fuentes"][FUENTE]["resultado"] == "reprocesado" and r3["publicar"]

    r4 = pipeline(crudo, salida, "--web")  # sin cambios, pero se pide web/ igual
    assert r4["fuentes"][FUENTE]["resultado"] == "sin cambios" and r4["web"] and not r4["publicar"]


def test_correr_falla_si_falta_el_original(tmp_path):
    (tmp_path / "crudo").mkdir()
    r = correr("pipeline/correr.py", "--crudo", tmp_path / "crudo", "--salida", tmp_path / "salida")
    assert r.returncode != 0
    assert "falta el original" in r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1])["publicar"] is False


# ------------------------------------------------------------------ publicar.py

@pytest.fixture
def procesado(crudo, tmp_path) -> tuple[Path, Path]:
    salida = tmp_path / "salida"
    resumen = tmp_path / "resumen.json"
    pipeline(crudo, salida, "--resumen", resumen)
    return salida, resumen


def test_publica_release_nuevo_como_latest(gh, procesado):
    salida, resumen = procesado
    r = correr("scripts/publicar.py", "subir", "--salida", salida, "--resumen", resumen)
    assert r.returncode == 0, r.stderr
    (tag, rel), = estado(gh).items()
    assert tag.startswith("datos-") and rel == {**rel, "draft": False, "latest": True}
    subidos = {p.name for p in (gh / tag).iterdir()}
    assert {"web.zip", "manifest.json", "observatorio.duckdb", "reporte_validacion.md", "observaciones.parquet",
            "territorios.parquet", "capturas_historial.parquet", "fuentes.parquet", "observaciones.csv",
            "territorios_segmento.parquet", "territorios_segmento.geojson"} <= subidos
    # Se creó como borrador y se publicó solo después de subir todo.
    llamadas = (gh / "llamadas.log").read_text().splitlines()
    orden = [next(i for i, linea in enumerate(llamadas) if linea.startswith(f"release {c}")) for c in
             ("create", "upload", "edit")]
    assert orden == sorted(orden) and "--draft" in llamadas[orden[0]]


def test_si_la_subida_falla_el_latest_anterior_queda_intacto(gh, procesado):
    salida, resumen = procesado
    assert correr("scripts/publicar.py", "subir", "--salida", salida, "--resumen", resumen).returncode == 0
    (bueno,) = estado(gh)
    antes = sorted(p.name for p in (gh / bueno).iterdir())

    r = correr("scripts/publicar.py", "subir", "--salida", salida, "--resumen", resumen,
               env={"GH_FALSO_FALLAR": "upload"})
    assert r.returncode != 0
    assert list(estado(gh)) == [bueno]  # el borrador fallido se borró
    assert estado(gh)[bueno]["latest"] is True
    assert sorted(p.name for p in (gh / bueno).iterdir()) == antes


def test_con_errores_no_se_publica(gh, tmp_path):
    resumen = tmp_path / "resumen.json"
    resumen.write_text(json.dumps({"fuentes": {}, "publicar": False, "errores": [FUENTE]}))
    r = correr("scripts/publicar.py", "subir", "--salida", tmp_path, "--resumen", resumen)
    assert r.returncode != 0 and estado(gh) == {}


def test_ciclo_semanal_sin_cambios_en_un_runner_limpio(gh, crudo, tmp_path):
    """Como en Actions: cada corrida empieza sin datos/salida y baja la publicación anterior."""
    def ciclo(n, *extra):
        salida, resumen = tmp_path / f"runner{n}", tmp_path / f"resumen{n}.json"
        assert correr("scripts/publicar.py", "bajar", "--salida", salida).returncode == 0
        res = pipeline(crudo, salida, "--resumen", resumen, *extra)
        r = correr("scripts/publicar.py", "subir", "--salida", salida, "--resumen", resumen)
        assert r.returncode == 0, r.stderr
        return res

    assert ciclo(1)["fuentes"][FUENTE]["resultado"] == "nuevo"
    (tag,) = estado(gh)
    assert ciclo(2)["fuentes"][FUENTE]["resultado"] == "sin cambios"
    assert list(estado(gh)) == [tag]  # no hay release nuevo
    historial = pd.read_parquet(gh / tag / "capturas_historial.parquet").resultado.tolist()
    assert historial == ["nuevo", "sin cambios"]  # pero el historial publicado se actualizó

    assert ciclo(3, "--forzar")["fuentes"][FUENTE]["resultado"] == "reprocesado"
    nuevos = [t for t in estado(gh) if t != tag]
    assert len(nuevos) == 1 and estado(gh)[nuevos[0]]["latest"] and not estado(gh)[tag]["latest"]


# ------------------------------------------------------------------ conseguir_originales.py

def fuentes_con_url(tmp_path, url: str) -> Path:
    carpeta = tmp_path / "fuentes"
    carpeta.mkdir()
    f = yaml.safe_load((RAIZ / "fuentes" / f"{FUENTE}.yml").read_text(encoding="utf-8"))
    f["url_descarga"] = url
    (carpeta / f"{FUENTE}.yml").write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
    return carpeta


def test_original_desde_crudos(gh, tmp_path):
    (gh / "crudos").mkdir(parents=True)
    shutil.copy(FIXTURES / "ine_2023_mini.zip", gh / "crudos" / ORIGINAL)
    (gh / "estado.json").write_text(json.dumps({"crudos": {"draft": False, "latest": False, "createdAt": "2026"}}))
    fuentes = fuentes_con_url(tmp_path, "http://no-se-usa.invalid/x.zip")
    r = correr("scripts/conseguir_originales.py", "--crudo", tmp_path / "crudo", "--fuentes", fuentes)
    assert r.returncode == 0, r.stderr
    assert "release crudos" in r.stdout
    assert (tmp_path / "crudo" / ORIGINAL).read_bytes() == (FIXTURES / "ine_2023_mini.zip").read_bytes()


def test_original_desde_la_fuente_se_agrega_a_crudos(gh, tmp_path):
    fuentes = fuentes_con_url(tmp_path, (FIXTURES / "ine_2023_mini.zip").as_uri())
    r = correr("scripts/conseguir_originales.py", "--crudo", tmp_path / "crudo", "--fuentes", fuentes)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "crudo" / ORIGINAL).exists()
    assert estado(gh)["crudos"]["latest"] is False  # crudos nunca es el "latest"
    assert (gh / "crudos" / ORIGINAL).exists()
    assert "--clobber" not in (gh / "llamadas.log").read_text().split("release upload")[-1]


def test_sin_crudos_ni_fuente_falla(gh, tmp_path):
    fuentes = fuentes_con_url(tmp_path, (tmp_path / "no-existe.zip").as_uri())
    r = correr("scripts/conseguir_originales.py", "--crudo", tmp_path / "crudo", "--fuentes", fuentes, "--espera", 0)
    assert r.returncode != 0 and "FALLA" in r.stderr


# ------------------------------------------------------------------ fuentes con carpeta de originales (F2.5d, #59)

ECH = "ine_ech_mercado_trabajo_departamental"


def crudo_ech(tmp_path, informes=("2024_09", "2026_09")) -> Path:
    """datos/crudo con ech_mt/ capturado desde los fixtures (sin red)."""
    sys.path.insert(0, str(RAIZ / "pipeline"))
    from ech_captura import capturar
    from ech_descubrimiento import Informe

    from comun.periodos import trimestre_movil

    w = "https://www5.ine.gub.uy/documents/ECH/"
    sitio = {f"{w}{i}.html": (FIXTURES / "ech_mt" / f"ech_mt_{i}.html").read_bytes() for i in informes}
    lista = [Informe(trimestre_movil(int(i[:4]), int(i[5:])), f"https://www.gub.uy/x-{i}", f"{w}{i}.html")
             for i in informes]
    c = tmp_path / "crudo_ech"
    capturar(lista, c, sitio.__getitem__, hoy="2026-11-18")
    return c


def test_subir_crudos_sube_cada_original_una_vez_y_el_registro(gh, tmp_path):
    c = crudo_ech(tmp_path)
    r = correr("scripts/crudos_carpeta.py", "subir", "--crudo", c, "--carpeta", "ech_mt")
    assert r.returncode == 0, r.stderr
    from ech_captura import leer_registro

    reg = leer_registro(c)
    subidos = sorted(p.name for p in (gh / "crudos").iterdir())
    assert [n for n in subidos if n.endswith(".html")] == sorted(f"ech_mt-{x['sha256'][:12]}.html" for x in reg)
    (registro,) = [n for n in subidos if n.endswith(".json")]
    assert registro.startswith("ech_mt-capturas-0002-")
    for x in reg:  # sin cambios
        assert (gh / "crudos" / f"ech_mt-{x['sha256'][:12]}.html").read_bytes() == (c / x["archivo"]).read_bytes()
    # otra vez: no sube nada (nunca reemplaza)
    antes = (gh / "llamadas.log").read_text().count("release upload")
    assert correr("scripts/crudos_carpeta.py", "subir", "--crudo", c, "--carpeta", "ech_mt").returncode == 0
    assert (gh / "llamadas.log").read_text().count("release upload") == antes


def test_bajar_crudos_reconstruye_la_carpeta_con_el_ultimo_registro(gh, tmp_path):
    c = crudo_ech(tmp_path, ("2024_09",))
    assert correr("scripts/crudos_carpeta.py", "subir", "--crudo", c, "--carpeta", "ech_mt").returncode == 0
    c2 = crudo_ech(tmp_path / "otro", ("2024_09", "2026_09"))
    assert correr("scripts/crudos_carpeta.py", "subir", "--crudo", c2, "--carpeta", "ech_mt").returncode == 0
    limpio = tmp_path / "runner"
    r = correr("scripts/crudos_carpeta.py", "bajar", "--crudo", limpio, "--carpeta", "ech_mt")
    assert r.returncode == 0, r.stderr
    from ech_captura import leer_registro, verificar

    reg = leer_registro(limpio)
    assert len(reg) == 2  # el registro más reciente
    for x in reg:
        verificar(limpio, x)
    # un asset alterado frena la bajada
    nombre = f"ech_mt-{reg[0]['sha256'][:12]}.html"
    (gh / "crudos" / nombre).write_bytes(b"otro contenido")
    r = correr("scripts/crudos_carpeta.py", "bajar", "--crudo", tmp_path / "runner2", "--carpeta", "ech_mt")
    assert r.returncode != 0 and "sha256" in r.stderr


def test_conseguir_originales_baja_tambien_las_carpetas(gh, tmp_path):
    c = crudo_ech(tmp_path)
    assert correr("scripts/crudos_carpeta.py", "subir", "--crudo", c, "--carpeta", "ech_mt").returncode == 0
    shutil.copy(FIXTURES / "ine_2023_mini.zip", gh / "crudos" / ORIGINAL)
    destino = tmp_path / "crudo"
    r = correr("scripts/conseguir_originales.py", "--crudo", destino, "--sin-subir")
    assert r.returncode == 0, r.stderr
    assert (destino / ORIGINAL).exists() and (destino / "ech_mt" / "capturas.json").exists()
    assert f"| {ECH} | `ech_mt/` (2 informes) | release crudos |" in r.stdout


def test_las_fuentes_a_procesar_son_las_activas_y_las_que_se_cargan_con_la_geografia_primero():
    from comun.registro import a_procesar, cargar_fuentes

    fuentes = cargar_fuentes(RAIZ / "fuentes")
    assert fuentes[ECH]["estado"] == "en preparación" and fuentes[ECH]["cargar"] is True
    assert [f["id"] for f in a_procesar(fuentes)] == [FUENTE, ECH]  # el Censo (territorios) antes que la ECH
