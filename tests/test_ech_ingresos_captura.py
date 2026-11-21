"""F3.4a (#137): captura de las planillas de ingresos del INE (AC-I4 parte local, AC-I5 y AC-I6 parte de captura).

Sin red: el «sitio» es un diccionario URL -> bytes con los fixtures de F3.1; una URL que no está da HTTP 404.
"""

from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import zipfile
from pathlib import Path

import pytest
from ech_ingresos_captura import CARPETA, ErrorCaptura, Planilla, capturar, leer_registro, planillas

from comun.registro import RAIZ, cargar_fuentes

FIX = Path(__file__).resolve().parent / "fixtures" / "ech_ingresos"
BASE = "https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/SERIES%20Y%20OTROS/ECH/Series%20hist%C3%B3ricas/Ingresos%20de%20las%20personas%20y%20los%20hogares/"
HOY = "2026-11-20"


def p(codigo):
    return Planilla(codigo, BASE + f"{codigo}.xlsx")


def sitio(archivos: dict[str, bytes]):
    """Descargador falso: una URL conocida devuelve sus bytes; cualquier otra, HTTP 404."""
    def bajar(url: str) -> bytes:
        if url not in archivos:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return archivos[url]
    return bajar


def fix(codigo):
    return (FIX / f"{codigo}.xlsx").read_bytes()


def otra_version(xlsx: bytes) -> bytes:
    """El mismo xlsx con un texto cambiado (una revisión del INE): otro sha256, sigue siendo xlsx."""
    entrada, salida = zipfile.ZipFile(io.BytesIO(xlsx)), io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for info in entrada.infolist():
            datos = entrada.read(info.filename)
            if info.filename == "xl/sharedStrings.xml":
                datos = datos.replace(b"noviembre 2026", b"diciembre 2026")
            z.writestr(info, datos)
    return salida.getvalue()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def test_planillas_salen_del_registro():
    """Solo las del conjunto mínimo (las que tienen indicador), con la URL tal como está en el registro."""
    ps = planillas(cargar_fuentes(RAIZ / "fuentes")["ine_ech_ingresos_series"])
    assert [x.codigo for x in ps] == ["ECHING07", "ECHING08", "ECHING09", "ECHING10", "ECHING11", "ECHING12",
                                      "ECHING13", "ECHING14", "ECHINGRESOS2", "ECHINGRESOS3"]
    assert all(x.url.startswith("https://www5.ine.gub.uy/") and x.url.endswith(f"/{x.codigo}.xlsx") for x in ps)


# AC-I4 (parte local)
def test_cada_planilla_se_guarda_sin_cambios_con_url_sha256_y_fecha(tmp_path):
    datos = {p("ECHING07").url: fix("ECHING07"), p("ECHING09").url: fix("ECHING09")}
    r = capturar([p("ECHING07"), p("ECHING09")], tmp_path, sitio(datos), hoy=HOY)
    assert (r.nuevas, r.sin_cambios, r.errores) == (2, 0, [])
    reg = leer_registro(tmp_path)
    assert [c["codigo"] for c in reg] == ["ECHING07", "ECHING09"]
    for c in reg:
        original = tmp_path / c["archivo"]
        assert c["archivo"] == f"{CARPETA}/{c['codigo']}.xlsx"
        assert original.read_bytes() == fix(c["codigo"])
        assert c["sha256"] == sha(original.read_bytes()) and c["url"] == p(c["codigo"]).url
        assert c["descargado"] == HOY and c["vigente"] is True
        assert c["id"] == f"ine_ech_ingresos_series:{c['sha256'][:12]}"


def test_sin_cambios_no_se_vuelve_a_guardar(tmp_path):
    datos = {p("ECHING07").url: fix("ECHING07")}
    capturar([p("ECHING07")], tmp_path, sitio(datos), hoy=HOY)
    r = capturar([p("ECHING07")], tmp_path, sitio(datos), hoy="2026-11-27")
    assert (r.nuevas, r.sin_cambios) == (0, 1)
    reg = leer_registro(tmp_path)
    assert len(reg) == 1 and reg[0]["descargado"] == HOY


# AC-I6 (parte de captura)
def test_un_archivo_que_cambia_es_una_captura_nueva_y_la_anterior_deja_de_ser_vigente(tmp_path):
    v1, v2 = fix("ECHING07"), otra_version(fix("ECHING07"))
    capturar([p("ECHING07")], tmp_path, sitio({p("ECHING07").url: v1}), hoy=HOY)
    r = capturar([p("ECHING07")], tmp_path, sitio({p("ECHING07").url: v2}), hoy="2026-12-15")
    assert r.nuevas == 1
    vieja, nueva = leer_registro(tmp_path)
    assert (vieja["vigente"], nueva["vigente"]) == (False, True)
    assert nueva["sha256"] == sha(v2) and nueva["descargado"] == "2026-12-15"
    # el original anterior no se pisa ni se borra
    assert (tmp_path / vieja["archivo"]).read_bytes() == v1
    assert (tmp_path / nueva["archivo"]).read_bytes() == v2
    assert nueva["archivo"] == f"{CARPETA}/ECHING07.{sha(v2)[:12]}.xlsx"


def test_si_el_ine_vuelve_a_una_version_anterior_esa_vuelve_a_ser_vigente(tmp_path):
    """A → B → A: no se guarda nada nuevo, vuelve a ser vigente la captura de A, y la corrida sigue con las demás."""
    a, b = fix("ECHING07"), otra_version(fix("ECHING07"))
    capturar([p("ECHING07")], tmp_path, sitio({p("ECHING07").url: a}), hoy=HOY)
    capturar([p("ECHING07")], tmp_path, sitio({p("ECHING07").url: b}), hoy="2026-12-15")
    r = capturar([p("ECHING07"), p("ECHING09")], tmp_path,
                 sitio({p("ECHING07").url: a, p("ECHING09").url: fix("ECHING09")}), hoy="2027-01-10")
    assert (r.nuevas, r.revertidas, r.errores) == (1, ["ECHING07"], [])
    reg = leer_registro(tmp_path)
    del07 = [c for c in reg if c["codigo"] == "ECHING07"]
    assert len(del07) == 2 and [c["vigente"] for c in del07] == [True, False] and del07[0]["sha256"] == sha(a)
    assert [c["codigo"] for c in reg if c["vigente"]] == ["ECHING07", "ECHING09"]


def test_el_contenido_de_otra_planilla_es_un_error_de_esa_planilla(tmp_path):
    datos = {p("ECHING07").url: fix("ECHING07"), p("ECHING08").url: fix("ECHING07"), p("ECHING09").url: fix("ECHING09")}
    r = capturar([p("ECHING07"), p("ECHING08"), p("ECHING09")], tmp_path, sitio(datos), hoy=HOY)
    assert r.nuevas == 2 and [e["codigo"] for e in r.errores] == ["ECHING08"]
    assert "ECHING07" in r.errores[0]["error"]
    assert [c["codigo"] for c in leer_registro(tmp_path)] == ["ECHING07", "ECHING09"]


# AC-I5 (parte de captura)
def test_un_archivo_con_error_queda_registrado_y_no_frena_los_demas(tmp_path):
    datos = {p("ECHING07").url: fix("ECHING07"), p("ECHING09").url: b"<html>Not Found</html>"}
    r = capturar([p("ECHING07"), p("ECHING08"), p("ECHING09")], tmp_path, sitio(datos), hoy=HOY)
    assert r.nuevas == 1
    errores = {e["codigo"]: e["error"] for e in r.errores}
    assert set(errores) == {"ECHING08", "ECHING09"}
    assert "404" in errores["ECHING08"] and "xlsx" in errores["ECHING09"]
    reg = json.loads((tmp_path / CARPETA / "capturas.json").read_text(encoding="utf-8"))
    assert [c["codigo"] for c in reg["capturas"]] == ["ECHING07"]
    assert reg["ultima_corrida"] == {"fecha": HOY, "errores": r.errores, "revertidas": []}
    assert not (tmp_path / CARPETA / "ECHING09.xlsx").exists()


def test_un_error_no_cambia_la_captura_vigente(tmp_path):
    capturar([p("ECHING07")], tmp_path, sitio({p("ECHING07").url: fix("ECHING07")}), hoy=HOY)
    r = capturar([p("ECHING07")], tmp_path, sitio({}), hoy="2026-11-27")
    assert len(r.errores) == 1 and leer_registro(tmp_path)[0]["vigente"] is True


def test_un_original_alterado_frena_la_captura(tmp_path):
    capturar([p("ECHING07")], tmp_path, sitio({p("ECHING07").url: fix("ECHING07")}), hoy=HOY)
    (tmp_path / CARPETA / "ECHING07.xlsx").write_bytes(b"otra cosa")
    with pytest.raises(ErrorCaptura, match="sha256"):
        capturar([p("ECHING07")], tmp_path, sitio({p("ECHING07").url: fix("ECHING07")}), hoy=HOY)


def test_solo_urls_oficiales(tmp_path):
    with pytest.raises(ErrorCaptura, match="oficial"):
        capturar([Planilla("ECHING07", "https://example.com/ECHING07.xlsx")], tmp_path, sitio({}), hoy=HOY)
