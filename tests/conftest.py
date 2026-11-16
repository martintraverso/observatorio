"""Configuración de los tests: sobre qué datos corren.

OBS_DATOS=fixture (por defecto)
    Corre el pipeline sobre tests/fixtures/ine_2023_mini.zip en una carpeta temporal,
    una vez por sesión. No necesita el zip original ni pasos previos. Es lo que corre en CI.

OBS_DATOS=completo
    Usa la salida ya generada en datos/salida/ a partir del zip completo del INE:
      python pipeline/territorios_2023.py datos/crudo/Unidades_Geoestadisticas_Censo_2023.zip
      OBS_DATOS=completo pytest -q
    Si la salida no existe, los tests fallan (no se saltean en silencio).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
PIPELINE = RAIZ / "pipeline" / "territorios_2023.py"
FIXTURES = RAIZ / "tests" / "fixtures"

MODOS = {
    "fixture": {
        "entrada": FIXTURES / "ine_2023_mini.zip",
        "esperado": FIXTURES / "esperado.yml",
    },
    "completo": {
        "entrada": RAIZ / "datos" / "crudo" / "Unidades_Geoestadisticas_Censo_2023.zip",
        "esperado": RAIZ / "pipeline" / "esperado" / "ine_2023_completo.yml",
        "salida": RAIZ / "datos" / "salida",
    },
}

MODO = os.environ.get("OBS_DATOS", "fixture")
if MODO not in MODOS:
    raise pytest.UsageError(f"OBS_DATOS debe ser uno de {sorted(MODOS)}, no {MODO!r}")


def pytest_report_header(config):
    return f"OBS_DATOS={MODO} · entrada {MODOS[MODO]['entrada'].relative_to(RAIZ)}"


@pytest.fixture(scope="session")
def modo() -> str:
    return MODO


@pytest.fixture(scope="session")
def entrada() -> Path:
    return MODOS[MODO]["entrada"]


@pytest.fixture(scope="session")
def esperado() -> dict:
    return yaml.safe_load(MODOS[MODO]["esperado"].read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def salida(tmp_path_factory) -> Path:
    if MODO == "completo":
        carpeta = MODOS["completo"]["salida"]
        if not (carpeta / "observatorio.duckdb").exists():
            pytest.fail(
                f"No hay salida en {carpeta.relative_to(RAIZ)}. Primero correr:\n"
                "  python pipeline/territorios_2023.py datos/crudo/Unidades_Geoestadisticas_Censo_2023.zip",
                pytrace=False,
            )
        return carpeta

    carpeta = tmp_path_factory.mktemp("salida_fixture")
    r = subprocess.run(
        [sys.executable, str(PIPELINE), str(MODOS["fixture"]["entrada"]),
         "--salida", str(carpeta), "--esperado", str(MODOS["fixture"]["esperado"])],
        capture_output=True, text=True, cwd=RAIZ,
    )
    if r.returncode != 0:
        pytest.fail(f"El pipeline falló sobre el fixture (código {r.returncode}):\n{r.stdout}\n{r.stderr}",
                    pytrace=False)
    return carpeta


@pytest.fixture(scope="session")
def con(salida):
    c = duckdb.connect(str(salida / "observatorio.duckdb"), read_only=True)
    yield c
    c.close()
