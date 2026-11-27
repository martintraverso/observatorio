"""scripts/verificar.py: qué pasos corre según los archivos cambiados."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verificar", RAIZ / "scripts" / "verificar.py")
verificar = importlib.util.module_from_spec(_spec)
sys.modules["verificar"] = verificar  # @dataclass lo busca ahí
_spec.loader.exec_module(verificar)


def nombres(archivos, **kw):
    return [p.nombre for p in verificar.plan(verificar.grupos(archivos), **kw)]


@pytest.mark.parametrize("archivos", [[], ["docs/SYSTEM.md"], ["README.md", "CLAUDE.md"], [".claude/proyecto.json"]])
def test_solo_docs_no_corre_nada(archivos):
    assert nombres(archivos) == []


def test_solo_app_no_rehace_la_web_ni_corre_pytest():
    assert nombres(["app/src/lib/datos.ts"]) == ["app: check", "app: vitest", "app: build", "app: e2e"]
    assert nombres(["app/src/lib/datos.ts"], e2e=False) == ["app: check", "app: vitest", "app: build"]


def test_tests_o_scripts_corren_solo_el_fixture():
    assert nombres(["tests/test_web.py"]) == ["ruff", "pytest (fixture)"]
    assert nombres(["scripts/publicar.py"]) == ["ruff", "pytest (fixture)"]


def test_un_cargador_rehace_la_web_y_corre_los_datos_completos():
    assert nombres(["pipeline/mec_anuario_cargar.py"]) == ["ruff", "pytest (fixture)", "web.py", "pytest (completo)"]
    assert nombres(["fuentes/mec_anuario_educacion.yml"]) == [
        "ruff", "pytest (fixture)", "web.py", "pytest (completo)"]


def test_web_py_cambia_lo_que_lee_la_app():
    n = nombres(["pipeline/web.py"])
    assert n == ["ruff", "pytest (fixture)", "web.py", "pytest (completo)",
                 "app: check", "app: vitest", "app: build", "app: e2e"]


def test_sin_web_py_no_corren_los_pasos_que_la_necesitan(tmp_path, monkeypatch):
    llamadas = []

    def falso(cmd, **kw):
        llamadas.append(cmd)
        return type("R", (), {"returncode": 1 if "pipeline/web.py" in cmd else 0})()

    monkeypatch.setattr(verificar.subprocess, "run", falso)
    pasos = verificar.plan({"datos", "app"})
    r = {n: e for n, e, _ in verificar.correr(pasos, tmp_path)}
    assert r["web.py"] == "FALLA"
    assert r["pytest (completo)"] == r["app: build"] == r["app: e2e"] == "SALTEADO"
    assert len(llamadas) == 1
