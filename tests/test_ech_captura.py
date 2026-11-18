"""F2.5b (#57): captura de los informes de mercado de trabajo (AC-L1 parte local, AC-L3).

Sin red: el «sitio» es un diccionario URL -> bytes; los informes son los fixtures recortados de F2.1.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from ech_captura import ErrorCaptura, capturar, leer_registro
from ech_descubrimiento import Informe

from comun.periodos import trimestre_movil

FIX = Path(__file__).resolve().parent / "fixtures" / "ech_mt"
W = "https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/HTML/ECH/Mercado%20de%20trabajo%20por%20%C3%A1rea%20geogr%C3%A1fica/"
PUB = "https://www.gub.uy/instituto-nacional-estadistica/comunicacion/publicaciones/mercado-trabajo-area-geografica-residencia-ech-"
URL_2026 = W + "2026/Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.html"
URL_2024 = W + "2024/Informe_departamental-Julio-Setiembre2024.html"
V11 = URL_2026.replace("v1_0", "v1_1")
HOY = "2026-11-18"


def informe(fin, url, pub):
    return Informe(trimestre_movil(*fin), PUB + pub, url)


INFORMES = [informe((2024, 9), URL_2024, "julio-setiembre-2024"), informe((2026, 9), URL_2026, "julio-setiembre-2026")]


class Sitio:
    def __init__(self):
        self.archivos = {URL_2024: (FIX / "ech_mt_2024_09.html").read_bytes(),
                         URL_2026: (FIX / "ech_mt_2026_09.html").read_bytes()}
        self.pedidas: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.pedidas.append(url)
        return self.archivos[url]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# AC-L1 (parte local)
def test_cada_informe_se_guarda_sin_cambios_con_url_sha256_y_fecha(tmp_path):
    sitio = Sitio()
    r = capturar(INFORMES, tmp_path, sitio, hoy=HOY)
    assert r.nuevas == 2 and r.sin_cambios == 0
    reg = leer_registro(tmp_path)
    assert [c["archivo"] for c in reg] == ["ech_mt/2024/Informe_departamental-Julio-Setiembre2024.html",
                                          "ech_mt/2026/Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.html"]
    for c, url in zip(reg, [URL_2024, URL_2026]):
        guardado = (tmp_path / c["archivo"]).read_bytes()
        assert guardado == sitio.archivos[url]  # sin cambios
        assert c["sha256"] == sha(guardado)
        assert (c["url"], c["descargado"], c["vigente"]) == (url, HOY, True)
        assert c["id"] == f"ine_ech_mercado_trabajo_departamental:{c['sha256'][:12]}"
    assert [c["periodo"] for c in reg] == ["2024-07/2024-09", "2026-07/2026-09"]
    assert reg[1]["pagina"] == PUB + "julio-setiembre-2026"
    # el registro es JSON legible, junto a los originales
    assert json.loads((tmp_path / "ech_mt" / "capturas.json").read_text(encoding="utf-8"))["capturas"] == reg


def test_una_segunda_corrida_no_vuelve_a_bajar_lo_capturado(tmp_path):
    capturar(INFORMES, tmp_path, Sitio(), hoy=HOY)
    otra = Sitio()
    r = capturar(INFORMES, tmp_path, otra, hoy="2026-11-19")
    assert otra.pedidas == [] and r.nuevas == 0 and r.sin_cambios == 2
    assert {c["descargado"] for c in leer_registro(tmp_path)} == {HOY}


def test_con_revisar_se_vuelve_a_bajar_y_si_no_cambio_no_hay_captura_nueva(tmp_path):
    capturar(INFORMES, tmp_path, Sitio(), hoy=HOY)
    otra = Sitio()
    r = capturar(INFORMES, tmp_path, otra, hoy="2026-11-19", revisar=True)
    assert len(otra.pedidas) == 2 and r.nuevas == 0 and r.sin_cambios == 2
    assert len(leer_registro(tmp_path)) == 2


# AC-L3
def test_una_version_nueva_es_otra_captura_y_la_anterior_queda_trazable(tmp_path):
    capturar(INFORMES, tmp_path, Sitio(), hoy=HOY)
    sitio = Sitio()
    sitio.archivos[V11] = sitio.archivos[URL_2026].replace(b"64,1", b"64,2", 1)
    r = capturar([INFORMES[0], informe((2026, 9), V11, "julio-setiembre-2026")], tmp_path, sitio, hoy="2026-12-01")
    assert sitio.pedidas == [V11] and r.nuevas == 1
    reg = {c["url"]: c for c in leer_registro(tmp_path)}
    assert reg[URL_2026]["vigente"] is False and reg[V11]["vigente"] is True and reg[URL_2024]["vigente"] is True
    assert (tmp_path / reg[URL_2026]["archivo"]).exists() and (tmp_path / reg[V11]["archivo"]).exists()
    assert reg[V11]["descargado"] == "2026-12-01" and reg[URL_2026]["id"] != reg[V11]["id"]


def test_si_cambia_el_contenido_de_la_misma_url_se_guardan_los_dos(tmp_path):
    capturar(INFORMES, tmp_path, Sitio(), hoy=HOY)
    sitio = Sitio()
    sitio.archivos[URL_2026] = sitio.archivos[URL_2026].replace(b"64,1", b"64,2", 1)
    r = capturar(INFORMES, tmp_path, sitio, hoy="2026-12-01", revisar=True)
    assert r.nuevas == 1
    viejas = [c for c in leer_registro(tmp_path) if c["url"] == URL_2026]
    assert [c["vigente"] for c in viejas] == [False, True]
    # el original no se mueve; el nuevo lleva su huella en el nombre
    assert viejas[0]["archivo"] == "ech_mt/2026/Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.html"
    assert viejas[1]["archivo"] == f"ech_mt/2026/Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.{viejas[1]['sha256'][:12]}.html"
    for c in viejas:
        assert sha((tmp_path / c["archivo"]).read_bytes()) == c["sha256"]  # ninguno se pierde ni se pisa


def test_un_original_modificado_en_disco_frena_la_captura(tmp_path):
    capturar(INFORMES, tmp_path, Sitio(), hoy=HOY)
    archivo = tmp_path / leer_registro(tmp_path)[0]["archivo"]
    archivo.write_bytes(archivo.read_bytes() + b" ")
    with pytest.raises(ErrorCaptura, match="no coincide"):
        capturar(INFORMES, tmp_path, Sitio(), hoy=HOY)


def test_nombres_de_archivo_inseguros_o_que_no_son_html():
    from ech_captura import nombre_de_archivo

    assert nombre_de_archivo(W + "2025/Bolet%C3%ADn_departamental-Noviembre-Enero_2026.html") == \
        "Boletín_departamental-Noviembre-Enero_2026.html"
    for malo in [W + "a%2F..%2Fb.html", W + "informe.pdf", W + "..%2F.html", W + "a%00.html", W + "x" * 300 + ".html"]:
        with pytest.raises(ErrorCaptura):
            nombre_de_archivo(malo)


def test_otra_url_con_el_mismo_nombre_no_pisa_un_original(tmp_path):
    capturar(INFORMES, tmp_path, Sitio(), hoy=HOY)
    otra = URL_2026.replace("/2026/", "/2026/corregido/")
    sitio = Sitio()
    sitio.archivos[otra] = sitio.archivos[URL_2026].replace(b"64,1", b"64,2", 1)
    capturar([informe((2026, 9), otra, "julio-setiembre-2026")], tmp_path, sitio, hoy="2026-12-01")
    for c in leer_registro(tmp_path):
        assert sha((tmp_path / c["archivo"]).read_bytes()) == c["sha256"]
    assert {c["url"]: c["vigente"] for c in leer_registro(tmp_path) if c["periodo"] == "2026-07/2026-09"} == {
        URL_2026: False, otra: True}
    capturar(INFORMES, tmp_path, Sitio(), hoy="2026-12-02")  # la corrida siguiente no falla


def test_una_corrida_cortada_deja_el_registro_coherente(tmp_path):
    sitio = Sitio()
    sitio.archivos[URL_2026] = None  # la segunda bajada falla

    def bajar(url):
        if sitio.archivos[url] is None:
            raise TimeoutError("se cortó")
        return sitio.archivos[url]

    with pytest.raises(TimeoutError):
        capturar(INFORMES, tmp_path, bajar, hoy=HOY)
    assert [c["url"] for c in leer_registro(tmp_path)] == [URL_2024]  # la primera quedó registrada
    r = capturar(INFORMES, tmp_path, Sitio(), hoy=HOY)  # y la siguiente corrida sigue desde ahí
    assert (r.nuevas, r.sin_cambios) == (1, 1)


def test_la_misma_version_en_otra_url_se_informa_sin_duplicar(tmp_path):
    capturar(INFORMES, tmp_path, Sitio(), hoy=HOY)
    movida = URL_2026.replace("/2026/", "/2026/otra-carpeta/")
    sitio = Sitio()
    sitio.archivos[movida] = sitio.archivos[URL_2026]
    r = capturar([INFORMES[0], informe((2026, 9), movida, "julio-setiembre-2026")], tmp_path, sitio, hoy=HOY)
    assert r.repetidas == [movida] and r.nuevas == 0
    assert len(leer_registro(tmp_path)) == 2


def test_si_la_url_vuelve_a_servir_una_version_anterior_esa_es_la_vigente(tmp_path):
    capturar(INFORMES, tmp_path, Sitio(), hoy=HOY)
    b = Sitio()
    b.archivos[URL_2026] = b.archivos[URL_2026].replace(b"64,1", b"64,2", 1)
    capturar(INFORMES, tmp_path, b, hoy="2026-12-01", revisar=True)
    capturar(INFORMES, tmp_path, Sitio(), hoy="2026-12-02", revisar=True)  # vuelve a la versión A
    vig = [c for c in leer_registro(tmp_path) if c["url"] == URL_2026]
    assert [c["vigente"] for c in vig] == [True, False]
