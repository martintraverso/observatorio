"""Pruebas del comportamiento del pipeline (AC-P1, P2, P6, P7, P8, P9).

Siempre corren sobre el fixture, en carpetas temporales: prueban cómo se comporta
el pipeline, no los datos. Los controles sobre los datos están en test_territorios.py.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest
import yaml
from conftest import FIXTURES, PIPELINE, RAIZ

from comun.capturas import ARCHIVO_HISTORIAL
from comun.registro import CAMPOS_OBLIGATORIOS, cargar_fuentes

FIXTURE_ZIP = FIXTURES / "ine_2023_mini.zip"
FIXTURE_ESPERADO = FIXTURES / "esperado.yml"

# Se importa en el subproceso antes que nada (sitecustomize): cualquier intento de red falla.
SIN_RED = '''
import socket

def _bloqueado(*args, **kwargs):
    raise OSError("red bloqueada en el test (AC-P1)")

socket.socket.connect = _bloqueado
socket.socket.connect_ex = _bloqueado
socket.create_connection = _bloqueado
socket.getaddrinfo = _bloqueado
'''


def correr(salida: Path, *extra, entrada: Path = FIXTURE_ZIP, esperado: Path = FIXTURE_ESPERADO, env=None):
    r = subprocess.run(
        [sys.executable, str(PIPELINE), str(entrada), "--salida", str(salida), "--esperado", str(esperado), *extra],
        capture_output=True, text=True, cwd=RAIZ, env={**os.environ, **(env or {})},
    )
    resumen = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
    return r, resumen


def historial(salida: Path) -> list[str]:
    return pd.read_parquet(salida / ARCHIVO_HISTORIAL).resultado.tolist()


@pytest.fixture(scope="module")
def sin_red(tmp_path_factory) -> dict:
    carpeta = tmp_path_factory.mktemp("sin_red")
    (carpeta / "sitecustomize.py").write_text(SIN_RED)
    env = {"PYTHONPATH": str(carpeta)}
    # El bloqueo funciona: un pedido HTTP falla con nuestro mensaje, sin llegar a la red.
    r = subprocess.run([sys.executable, "-c", "import urllib.request; urllib.request.urlopen('http://example.com')"],
                       capture_output=True, text=True, env={**os.environ, **env})
    assert r.returncode != 0 and "red bloqueada" in r.stderr
    return env


@pytest.fixture(scope="module")
def corrida_a(tmp_path_factory, sin_red) -> Path:
    """Primera corrida, sin red, en una carpeta vacía."""
    salida = tmp_path_factory.mktemp("corrida_a")
    r, resumen = correr(salida, env=sin_red)
    assert r.returncode == 0, r.stderr
    assert resumen["resultado"] == "nuevo"
    return salida


@pytest.fixture(scope="module")
def corrida_b(tmp_path_factory) -> Path:
    salida = tmp_path_factory.mktemp("corrida_b")
    r, _ = correr(salida)
    assert r.returncode == 0, r.stderr
    return salida


# AC-P1
def test_reconstruye_desde_cero_sin_red(corrida_a):
    import territorios_2023

    faltan = [s for s in territorios_2023.SALIDAS if not (corrida_a / s).exists()]
    assert faltan == []
    assert (corrida_a / ARCHIVO_HISTORIAL).exists()


# AC-P2
def test_dos_corridas_dan_las_mismas_observaciones(corrida_a, corrida_b):
    def leer(salida):
        obs = pd.read_parquet(salida / "observaciones.parquet")
        return obs.sort_values(["territorio_id", "indicador", "periodo"]).reset_index(drop=True)

    a, b = leer(corrida_a), leer(corrida_b)
    assert len(a) > 0
    pd.testing.assert_frame_equal(a, b)
    ca, cb = (pd.read_parquet(s / "capturas.parquet") for s in (corrida_a, corrida_b))
    assert ca.drop(columns="fecha_proceso").equals(cb.drop(columns="fecha_proceso"))


# AC-P6
def test_control_con_falla_sale_con_error_y_lista_en_stderr(tmp_path):
    esperado = yaml.safe_load(FIXTURE_ESPERADO.read_text(encoding="utf-8"))
    esperado["territorios_por_nivel"]["segmento"] += 1
    esperado["departamentos_con_secciones"] += 1
    malo = tmp_path / "esperado_malo.yml"
    malo.write_text(yaml.safe_dump(esperado))

    r, resumen = correr(tmp_path / "salida", esperado=malo)
    assert r.returncode != 0
    assert resumen["controles_falla"] == 2
    fallas = [linea for linea in r.stderr.splitlines() if linea.startswith("FALLA: ")]
    assert len(fallas) == 2
    assert any("territorios de nivel segmento" in f for f in fallas)
    assert any("departamentos con secciones" in f for f in fallas)
    assert historial(tmp_path / "salida") == ["error"]


# AC-P7
def test_reporte_tiene_conteos_controles_y_comparacion(corrida_a):
    reporte = (corrida_a / "reporte_validacion.md").read_text(encoding="utf-8")
    esperado = yaml.safe_load(FIXTURE_ESPERADO.read_text(encoding="utf-8"))
    for nivel, n in esperado["territorios_por_nivel"].items():
        assert f"| {nivel} | {n} |" in reporte
    controles = [linea for linea in reporte.split("## Controles")[1].split("##")[0].splitlines()
                 if linea.startswith("| ") and not linea.startswith("| Control")]
    assert len(controles) >= 18
    assert all(" | OK | " in c or " | FALLA | " in c for c in controles)
    assert "## Departamento vs. suma de secciones" in reporte
    assert "| 07 | Flores | 26.271 | 25.738 | 533 |" in reporte


def test_reporte_se_regenera_en_cada_corrida(tmp_path):
    salida = tmp_path / "salida"
    correr(salida)
    (salida / "reporte_validacion.md").write_text("viejo")
    r, _ = correr(salida, "--forzar")
    assert r.returncode == 0, r.stderr
    assert (salida / "reporte_validacion.md").read_text(encoding="utf-8").startswith("# Reporte de validación")


# AC-P8
def test_mismo_original_no_se_reprocesa(tmp_path):
    salida = tmp_path / "salida"
    r, resumen = correr(salida)
    assert resumen["resultado"] == "nuevo"
    obs = salida / "observaciones.parquet"
    antes = obs.stat().st_mtime_ns

    r, resumen = correr(salida)
    assert r.returncode == 0, r.stderr
    assert resumen["resultado"] == "sin cambios"
    assert obs.stat().st_mtime_ns == antes  # no se reescribió
    assert "· sin cambios" in (salida / "reporte_validacion.md").read_text(encoding="utf-8")

    r, resumen = correr(salida, "--forzar")
    assert resumen["resultado"] == "reprocesado"
    assert obs.stat().st_mtime_ns != antes

    # Otro original (mismo contenido, otro sha256: cambia el comentario del zip) -> se procesa.
    otro = tmp_path / "otro.zip"
    shutil.copy(FIXTURE_ZIP, otro)
    with zipfile.ZipFile(otro, "a") as z:
        z.comment = b"otra captura"
    r, resumen = correr(salida, entrada=otro)
    assert resumen["resultado"] == "nuevo"

    assert historial(salida) == ["nuevo", "sin cambios", "reprocesado", "nuevo"]
    h = pd.read_parquet(salida / ARCHIVO_HISTORIAL)
    assert h.sha256.str.len().eq(64).all() and h.archivo.ne("").all()


def test_sin_cambios_exige_salidas_completas(tmp_path):
    salida = tmp_path / "salida"
    correr(salida)
    (salida / "observaciones.parquet").unlink()
    r, resumen = correr(salida)
    assert resumen["resultado"] == "reprocesado"
    assert (salida / "observaciones.parquet").exists()


# AC-P9 (el registro completo se revisa a mano; acá, que cada archivo tenga los campos y cargue)
def test_registro_de_fuentes_completo():
    archivos = sorted((RAIZ / "fuentes").glob("*.yml"))
    assert archivos
    fuentes = cargar_fuentes(RAIZ / "fuentes")  # falla si algún yml no cumple
    assert set(fuentes) == {p.stem for p in archivos}
    for f in fuentes.values():
        assert all(f.get(c) not in (None, "", []) for c in CAMPOS_OBLIGATORIOS)
        if f.get("capas"):
            assert f.get("version_geo")


def test_tabla_fuentes_tiene_todo_el_registro(con):
    ids = {r[0] for r in con.execute("select id from fuentes").fetchall()}
    assert ids == {p.stem for p in (RAIZ / "fuentes").glob("*.yml")}
    assert con.execute("select estado, nivel_mas_detallado from fuentes "
                       "where id = 'ine_unidades_geoestadisticas_2023'").fetchone() == ("activa", "segmento")
