"""F2.5a (#56): descubrimiento de los informes de mercado de trabajo en el listado oficial del INE (AC-L2).

Sin red: las páginas son el <main> de páginas reales del listado (0, 10 y 11, la primera vacía) y de las 13
publicaciones que enlazan, guardadas por scripts/crear_fixtures_ech.py --descubrimiento.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ech_descubrimiento import (
    LISTADO,
    ErrorDescubrimiento,
    bajar_texto,
    descubrir,
    enlace_al_informe,
    publicaciones_del_listado,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "ech_mt" / "descubrimiento"
PUB = "https://www.gub.uy/instituto-nacional-estadistica/comunicacion/publicaciones/" \
      "mercado-trabajo-area-geografica-residencia-ech-"
ENCONTRADOS = ["2022-02", "2022-03", "2022-04", "2022-05", "2022-06", "2022-07", "2022-08", "2022-09", "2022-10",
               "2026-06", "2026-07", "2026-08", "2026-09"]


def leer(nombre: str) -> str:
    return (FIX / nombre).read_text(encoding="utf-8")


def sin_publicaciones(html: str) -> str:
    """La página del listado sin sus resultados de publicaciones (quedan los del calendario)."""
    return re.sub(r'<li class="Media[" ](?:(?!</li>).)*?comunicacion/publicaciones/.*?</li>', "", html, flags=re.S)


def con_total(html: str, n: int | None) -> str:
    total = re.compile(r"Mostrando[^<]*resultados")
    return total.sub("", html) if n is None else total.sub(f"Mostrando 1 - 10 de {n} resultados", html)


class Sitio:
    """Sirve las páginas guardadas. Las páginas 0, 1 y 2 del listado son las reales 0, 10 y 11 (con el total
    del contador ajustado a los 19 resultados que suman las dos primeras)."""

    def __init__(self, cambios: dict[str, str] | None = None, total: int | None = 19):
        self.paginas = {f"{LISTADO}?page={i}": con_total(leer(f"listado_{n}.html"), total)
                        for i, n in enumerate([0, 10, 11])}
        for f in FIX.glob("pub_*.html"):
            self.paginas[PUB + f.stem.removeprefix("pub_")] = f.read_text(encoding="utf-8")
        self.paginas.update(cambios or {})
        self.pedidas: list[str] = []

    def __call__(self, url: str) -> str:
        self.pedidas.append(url)
        return self.paginas[url]


def test_publicaciones_del_listado():
    assert publicaciones_del_listado(leer("listado_0.html")) == [
        PUB + s for s in ["abril-junio-2026", "julio-setiembre-2026", "junio-agosto-2026", "mayo-julio-2026"]]
    assert len(publicaciones_del_listado(leer("listado_10.html"))) == 9
    assert publicaciones_del_listado(leer("listado_11.html")) == []


def test_enlace_al_informe_en_la_publicacion():
    assert enlace_al_informe(leer("pub_julio-setiembre-2026.html")) == (
        "https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/HTML/ECH/Mercado%20de%20trabajo%20por%20"
        "%C3%A1rea%20geogr%C3%A1fica/2026/Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.html")
    assert enlace_al_informe(leer("pub_febrero-2022.html")).endswith("Residencia%20-%20feb%202022.html")
    # la misma URL, escrita con o sin codificar y con un fragmento, es un solo enlace
    assert enlace_al_informe(
        "<main><a href='https://www5.ine.gub.uy/documents/Demografía/Informe (junio 2026).html#c1'>a</a>"
        "<a href='https://www5.ine.gub.uy/documents/Demograf%C3%ADa/Informe%20%28junio%202026%29.html'>b</a>"
        "</main>") == "https://www5.ine.gub.uy/documents/Demograf%C3%ADa/Informe%20%28junio%202026%29.html"
    assert enlace_al_informe("<main><a href='https://example.com/informe.html'>x</a></main>") is None
    assert enlace_al_informe("<main>sin enlaces</main>") is None
    with pytest.raises(ErrorDescubrimiento, match="más de un"):
        enlace_al_informe("<main><a href='https://www5.ine.gub.uy/documents/a.html'>a</a>"
                          "<a href='https://www5.ine.gub.uy/documents/b.html'>b</a></main>")


# AC-L2
def test_recorre_el_listado_hasta_una_pagina_vacia():
    sitio = Sitio()
    r = descubrir(sitio)
    assert [i.periodo.etiqueta[-7:] for i in r.informes] == ENCONTRADOS
    # con el contador, para al ver los 19 resultados; sin contador, en la primera página vacía
    assert [u for u in sitio.pedidas if u.startswith(LISTADO)] == [f"{LISTADO}?page={i}" for i in range(2)]
    sin_contador = Sitio(total=None)
    assert len(descubrir(sin_contador).informes) == 13
    assert [u for u in sin_contador.pedidas if u.startswith(LISTADO)] == [f"{LISTADO}?page={i}" for i in range(3)]
    jul_set = r.informes[-1]
    assert (jul_set.periodo.etiqueta, str(jul_set.periodo.inicio), str(jul_set.periodo.fin)) == (
        "2026-07/2026-09", "2026-07-01", "2026-09-30")
    assert jul_set.pagina == PUB + "julio-setiembre-2026"
    assert jul_set.url.endswith("Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.html")
    feb = r.informes[0]
    assert (feb.periodo.etiqueta, feb.url.split("/")[-1]) == (
        "2021-12/2022-02", "Mercado%20Laboral%20por%20%C3%81rea%20Geogr%C3%A1fica%20de%20Residencia%20-%20feb%202022.html")


def test_un_mes_que_falta_se_informa_sin_fallar():
    r = descubrir(Sitio())
    # entre 2022-02 y 2026-09 hay 56 meses; en estas páginas aparecen 13
    assert len(r.faltantes) == 56 - 13
    assert r.faltantes[0] == "2022-11" and r.faltantes[-1] == "2026-05"
    assert set(r.faltantes).isdisjoint(ENCONTRADOS)
    assert r.resumen()["encontrados"] == 13 and r.resumen()["faltantes"] == r.faltantes


def test_una_publicacion_sin_enlace_se_informa():
    sin = Sitio({PUB + "mayo-2022": "<html><body><main>Sin archivo</main></body></html>"})
    r = descubrir(sin)
    assert r.sin_enlace == [PUB + "mayo-2022"]
    assert "2022-05" in r.faltantes


def test_periodo_de_la_publicacion_y_del_archivo_tienen_que_coincidir():
    otro = leer("pub_junio-2022.html").replace("JUNIO-2022", "JULIO-2022")
    with pytest.raises(ErrorDescubrimiento, match="no coincide"):
        descubrir(Sitio({PUB + "junio-2022": otro}))


def test_meses_repetidos_se_informan():
    copia = PUB + "julio-setiembre-2026-0"
    listado = leer("listado_0.html").replace("residencia-ech-mayo-julio-2026", "residencia-ech-julio-setiembre-2026-0")
    r = descubrir(Sitio({f"{LISTADO}?page=0": con_total(listado, 19), copia: leer("pub_julio-setiembre-2026.html")}))
    assert r.repetidos == {"2026-07/2026-09": [PUB + "julio-setiembre-2026", copia]}


def test_el_listado_tiene_un_limite_de_paginas():
    infinito = Sitio()
    infinito.paginas = {**infinito.paginas, **{f"{LISTADO}?page={i}": leer("listado_0.html") for i in range(100)}}
    with pytest.raises(ErrorDescubrimiento, match="páginas"):
        descubrir(infinito, max_paginas=5)


def test_solo_sitios_oficiales():
    with pytest.raises(ErrorDescubrimiento, match="oficiales"):
        bajar_texto("https://example.com/listado")


def test_el_listado_es_el_del_registro_de_la_fuente():
    from comun.registro import RAIZ, cargar_fuentes

    assert cargar_fuentes(RAIZ / "fuentes")["ine_ech_mercado_trabajo_departamental"]["pagina"] == LISTADO


def test_una_pagina_con_solo_eventos_del_calendario_no_corta_el_recorrido():
    cero = leer("listado_0.html")
    solo_calendario = sin_publicaciones(cero)
    assert publicaciones_del_listado(solo_calendario) == [] and "calendario-actividades" in solo_calendario
    sitio = Sitio(total=None)
    sitio.paginas[f"{LISTADO}?page=0"] = con_total(solo_calendario, None)
    r = descubrir(sitio)
    assert [i.periodo.etiqueta[-7:] for i in r.informes] == ENCONTRADOS[:9]  # las de la página siguiente


def test_si_el_contador_no_coincide_con_lo_recorrido_falla():
    with pytest.raises(ErrorDescubrimiento, match="109 resultados"):
        descubrir(Sitio(total=109))


def test_publicaciones_con_otro_nombre_se_informan():
    otro = leer("listado_10.html").replace("residencia-ech-marzo-2022", "residencia-marzo-2022")
    r = descubrir(Sitio({f"{LISTADO}?page=1": con_total(otro, 19)}))
    assert r.otras == [PUB.replace("-ech-", "-") + "marzo-2022"]
    assert "2022-03" in r.faltantes


def test_redireccion_fuera_de_los_sitios_oficiales(monkeypatch):
    class Respuesta:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def geturl(self):
            return "https://example.com/otra"

        def read(self):
            return b"x"

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Respuesta())
    with pytest.raises(ErrorDescubrimiento, match="fuera de los sitios oficiales"):
        bajar_texto(f"{LISTADO}?page=0")


def test_una_primera_pagina_sin_resultados_falla():
    sitio = Sitio(total=None)
    sitio.paginas[f"{LISTADO}?page=0"] = leer("listado_0.html").replace('<li class="Media"', '<li class="u-x Media"')
    with pytest.raises(ErrorDescubrimiento, match="primera página"):
        descubrir(sitio)
