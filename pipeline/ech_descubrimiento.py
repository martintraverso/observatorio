"""F2.5a: descubrimiento de los informes «Mercado de trabajo por área geográfica de residencia» (INE, ECH).

No hay un patrón estable de URL (F2.1, #40). Por eso se recorre el listado oficial de la temática
(`?page=0, 1, …` hasta una página sin resultados), se abre cada publicación y se lee en ella el enlace al
HTML del informe en www5.ine.gub.uy. Así se arma la lista de informes desde 2022-02 hasta el último, y se
informa qué meses faltan: que falte un mes no es un error (AC-L2).

`descubrir(bajar)` recibe la función que trae cada página, así los tests no usan la red.

Uso: python pipeline/ech_descubrimiento.py [--salida descubrimiento.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NamedTuple
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from ech_mercado_trabajo import ErrorInforme, periodo_de_nombre

from comun.periodos import Periodo

LISTADO = "https://www.gub.uy/instituto-nacional-estadistica/tematica/mercado-trabajo-area-geografica-residencia"
PUBLICACIONES = "/instituto-nacional-estadistica/comunicacion/publicaciones/mercado-trabajo-area-geografica-residencia-ech-"
DOMINIOS_OFICIALES = ("https://www5.ine.gub.uy/", "https://www.gub.uy/instituto-nacional-estadistica/")
INFORMES = "https://www5.ine.gub.uy/documents/"
PRIMER_MES = (2022, 2)  # desde febrero de 2022 la ECH publica estimaciones mensuales (MA3)

# El listado mezcla publicaciones con eventos del calendario de difusión: cada resultado es un <li class="Media">.
RESULTADO = re.compile(r'<li class="Media[" ](.*?)</li>', re.S)
DESTINO = re.compile(r'(?:about|href)="(?:https://www\.gub\.uy)?(/instituto-nacional-estadistica/[^"#?]+)"')
TOTAL = re.compile(r"Mostrando\s+\d+\s*-\s*\d+\s+de\s+(\d+)\s+resultados")
ENLACE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)


class ErrorDescubrimiento(ValueError):
    pass


class Informe(NamedTuple):
    periodo: Periodo
    pagina: str  # página de la publicación en gub.uy
    url: str     # HTML del informe en www5.ine.gub.uy


@dataclass
class Resultado:
    informes: list[Informe]
    faltantes: list[str] = field(default_factory=list)   # meses (AAAA-MM, mes final) sin informe
    sin_enlace: list[str] = field(default_factory=list)  # publicaciones sin enlace a un HTML
    otras: list[str] = field(default_factory=list)  # resultados en publicaciones/ con otro nombre (no se leen)
    repetidos: dict[str, list[str]] = field(default_factory=dict)  # período -> publicaciones

    def resumen(self) -> dict:
        return {
            "encontrados": len(self.informes),
            "desde": self.informes[0].periodo.etiqueta if self.informes else None,
            "hasta": self.informes[-1].periodo.etiqueta if self.informes else None,
            "faltantes": self.faltantes, "sin_enlace": self.sin_enlace, "repetidos": self.repetidos, "otras": self.otras,
            "informes": [{"periodo": i.periodo.etiqueta, "pagina": i.pagina, "url": i.url} for i in self.informes],
        }


def normalizar(url: str) -> str:
    """La misma URL escrita con o sin codificar ('Demografía' o 'Demograf%C3%ADa') queda igual.
    Solo se normaliza la ruta (sin el fragmento #…); '%2F' se mantiene."""
    u = urlsplit(url.strip())
    ruta = "/".join(quote(unquote(parte), safe="") for parte in u.path.split("/"))
    return urlunsplit((u.scheme, u.netloc, ruta, u.query, ""))


def resultados_del_listado(html: str) -> list[str]:
    """Rutas de todos los resultados de una página del listado (publicaciones y eventos del calendario)."""
    rutas = []
    for item in RESULTADO.findall(html):
        destino = DESTINO.search(item)
        if not destino:
            raise ErrorDescubrimiento(f"Un resultado del listado no tiene enlace: {item[:200]!r}")
        rutas.append(destino.group(1))
    return rutas


def publicaciones_del_listado(html: str) -> list[str]:
    """URLs de las publicaciones de mercado de trabajo de una página del listado."""
    return sorted({"https://www.gub.uy" + r for r in resultados_del_listado(html) if r.startswith(PUBLICACIONES)})


def total_del_listado(html: str) -> int | None:
    """N de «Mostrando 1 - 10 de N resultados», o None si la página no lo trae."""
    m = TOTAL.search(html)
    return int(m.group(1)) if m else None


def enlace_al_informe(html: str) -> str | None:
    """El enlace al HTML del informe en www5.ine.gub.uy, o None si la publicación no lo trae."""
    enlaces = {normalizar(u) for u in ENLACE.findall(html)}
    informes = sorted(u for u in enlaces if u.startswith(INFORMES) and u.lower().endswith(".html"))
    if len(informes) > 1:
        raise ErrorDescubrimiento(f"La publicación enlaza más de un informe: {informes}")
    return informes[0] if informes else None


def periodo_de_publicacion(pagina: str, url: str) -> Periodo:
    """Período según el nombre de la publicación y el del archivo; si los dos lo traen, tienen que coincidir."""
    try:
        de_pagina = periodo_de_nombre(pagina.rsplit("-ech-", 1)[-1])
        de_archivo = periodo_de_nombre(unquote(url.rsplit("/", 1)[-1]))
    except ErrorInforme as e:
        raise ErrorDescubrimiento(f"{pagina}: {e}") from None
    if de_pagina and de_archivo and de_pagina != de_archivo:
        raise ErrorDescubrimiento(f"{pagina}: el período {de_pagina.etiqueta} no coincide con el del archivo "
                                  f"{de_archivo.etiqueta} ({url})")
    if not (de_pagina or de_archivo):
        raise ErrorDescubrimiento(f"{pagina}: no se encontró el período")
    return de_pagina or de_archivo


def meses(desde: tuple[int, int], hasta: tuple[int, int]) -> list[str]:
    (a, m), salida = desde, []
    while (a, m) <= hasta:
        salida.append(f"{a}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return salida


def descubrir(bajar: Callable[[str], str], max_paginas: int = 50) -> Resultado:
    """Recorre el listado y cada publicación (AC-L2)."""
    vistos: list[str] = []  # todos los resultados (publicaciones y calendario), en orden
    total = None
    for n in range(max_paginas + 1):
        if n == max_paginas:
            raise ErrorDescubrimiento(f"El listado no terminó en {max_paginas} páginas")
        html = bajar(f"{LISTADO}?page={n}")
        total = total if total is not None else total_del_listado(html)
        resultados = resultados_del_listado(html)
        if not resultados:
            if n == 0:
                raise ErrorDescubrimiento("La primera página del listado no trae resultados: ¿cambió la página?")
            break  # página sin resultados de ningún tipo
        vistos += [r for r in resultados if r not in vistos]
        if total is not None and len(vistos) >= total:
            break
    if total is not None and len(vistos) != total:
        raise ErrorDescubrimiento(f"El listado dice {total} resultados y se recorrieron {len(vistos)}")
    publicaciones = ["https://www.gub.uy" + r for r in vistos if r.startswith(PUBLICACIONES)]
    otras = ["https://www.gub.uy" + r for r in vistos
             if "/comunicacion/publicaciones/" in r and not r.startswith(PUBLICACIONES)]

    informes, sin_enlace = [], []
    for pagina in publicaciones:
        url = enlace_al_informe(bajar(pagina))
        if url is None:
            sin_enlace.append(pagina)
        else:
            informes.append(Informe(periodo_de_publicacion(pagina, url), pagina, url))
    informes.sort(key=lambda i: (i.periodo.fin, i.pagina))

    por_periodo: dict[str, list[str]] = {}
    for i in informes:
        por_periodo.setdefault(i.periodo.etiqueta, []).append(i.pagina)
    encontrados = {f"{i.periodo.fin.year}-{i.periodo.fin.month:02d}" for i in informes}
    ultimo = (informes[-1].periodo.fin.year, informes[-1].periodo.fin.month) if informes else PRIMER_MES
    return Resultado(informes=informes, faltantes=[m for m in meses(PRIMER_MES, ultimo) if m not in encontrados],
                     sin_enlace=sin_enlace, repetidos={k: v for k, v in por_periodo.items() if len(v) > 1},
                     otras=otras)


def bajar_texto(url: str, timeout: int = 60) -> str:
    """Trae una página, solo de los sitios oficiales del INE (también después de redirecciones)."""
    return bajar_bytes(url, timeout).decode("utf-8")


def bajar_bytes(url: str, timeout: int = 180) -> bytes:
    """Trae un archivo sin modificarlo, solo de los sitios oficiales del INE (también después de redirecciones)."""
    if not url.startswith(DOMINIOS_OFICIALES):
        raise ErrorDescubrimiento(f"Solo se admiten sitios oficiales del INE: {url}")
    pedido = urllib.request.Request(url, headers={"User-Agent": "observatorio-uruguay/1.0"})
    with urllib.request.urlopen(pedido, timeout=timeout) as r:
        if not r.geturl().startswith(DOMINIOS_OFICIALES):
            raise ErrorDescubrimiento(f"La página terminó fuera de los sitios oficiales del INE: {r.geturl()}")
        return r.read()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, help="guardar el resumen en este JSON")
    args = ap.parse_args(argv)
    resumen = descubrir(bajar_texto).resumen()
    texto = json.dumps(resumen, ensure_ascii=False, indent=2)
    if args.salida:
        args.salida.write_text(texto + "\n", encoding="utf-8")
    print(json.dumps({k: resumen[k] for k in ("encontrados", "desde", "hasta", "faltantes", "sin_enlace",
                                              "repetidos", "otras")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
