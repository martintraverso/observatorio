"""Pruebas unitarias de pipeline/comun."""

from __future__ import annotations

import zipfile

import pytest

from comun.capturas import Historial, nueva_captura
from comun.controles import Controles
from comun.entrada import extraer_zip
from comun.registro import cargar_fuentes, validar_fuente


def captura(sha="a" * 64, fecha="2026-01-01T00:00:00+00:00"):
    return nueva_captura("prueba", "original.zip", sha, fecha)


def test_captura_exige_archivo_y_sha256():
    with pytest.raises(ValueError):
        nueva_captura("prueba", "original.zip", "", "2026-01-01")
    with pytest.raises(ValueError):
        nueva_captura("prueba", "", "a" * 64, "2026-01-01")
    assert captura()["id"] == "prueba:aaaaaaaaaaaa"


def test_historial_es_append_only_y_ignora_errores(tmp_path):
    h = Historial(tmp_path)
    assert h.ultima_procesada("prueba") is None
    h.agregar(captura("a" * 64), "nuevo")
    h.agregar(captura("b" * 64), "error", "falló")
    h.agregar(captura("a" * 64), "sin cambios")
    assert h.leer().resultado.tolist() == ["nuevo", "error", "sin cambios"]
    assert h.ultima_procesada("prueba")["sha256"] == "a" * 64
    assert h.ultima_procesada("otra") is None
    with pytest.raises(ValueError):
        h.agregar(captura(), "inventado")


def test_controles_codigo_de_salida(capsys):
    import sys

    c = Controles()
    c.chk("bien", True)
    assert c.informar(sys.stderr) == 0
    c.chk("mal", False, "detalle")
    assert c.informar(sys.stderr) == 1
    assert "FALLA: mal — detalle" in capsys.readouterr().err


def test_zip_con_ruta_insegura_se_rechaza(tmp_path):
    malo = tmp_path / "malo.zip"
    with zipfile.ZipFile(malo, "w") as z:
        z.writestr("../fuera.txt", "x")
    (tmp_path / "destino").mkdir()
    with pytest.raises(ValueError, match="Ruta insegura"):
        extraer_zip(malo, tmp_path / "destino")
    assert not (tmp_path / "fuera.txt").exists()


def test_registro_detecta_campos_faltantes(tmp_path):
    (tmp_path / "x.yml").write_text("id: x\nnombre: X\nestado: inventado\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        cargar_fuentes(tmp_path)
    assert "falta 'organismo'" in str(e.value)
    assert "estado 'inventado'" in str(e.value)


def test_registro_exige_nivel_mas_detallado_publicado():
    f = {"id": "x", "niveles_publicados": ["departamento"], "nivel_mas_detallado": "segmento"}
    assert any("nivel_mas_detallado" in e for e in validar_fuente(f, "x.yml"))


def test_fuente_activa_necesita_original_y_script_existente():
    base = {"id": "x", "estado": "activa", "niveles_publicados": ["departamento"],
            "nivel_mas_detallado": "departamento"}
    errores = validar_fuente(base, "x.yml")
    assert any("'archivo_original'" in e for e in errores) and any("'script'" in e for e in errores)
    errores = validar_fuente({**base, "archivo_original": "a/b.zip", "script": "pipeline/no_existe.py"}, "x.yml")
    assert any("no existe el script" in e for e in errores) and any("sin carpetas" in e for e in errores)
    errores = validar_fuente({**base, "estado": "a relevar"}, "x.yml")
    assert not any("archivo_original" in e or "script" in e for e in errores)  # solo las activas
