"""Fixtures de las «Series históricas ECH Ingresos de las personas y los hogares» (INE) — F3.1 (#125).

Lee la página oficial del INE, toma de ella la URL de cada archivo (no se arma: algunos enlaces apuntan a la
carpeta «Ingresos 2024/»), baja ECHING07, ECHING09 y ECHINGRESOS2, guarda en tests/fixtures/ech_ingresos/ un
recorte de cada uno y anota en fixtures.yml el código, el título del enlace, la URL, el sha256 y el tamaño del
original.

Recorte: cada xlsx trae una sola hoja con ~550.000 celdas vacías con formato (hasta la columna XFD), que es lo
que lo hace pesar 1,4–2,3 MB. Se quitan del XML de la hoja las celdas fuera de A:H y las filas después de la 120,
y se ajustan `dimension` y `spans`. Todo lo demás del archivo queda byte a byte: valores, fórmulas de los
totales anuales con su valor calculado, textos compartidos, estilos, celdas combinadas y notas al pie. Los
originales completos se capturan en F3.4 (datos/crudo/ech_ingresos/ y release crudos).

Uso: python scripts/crear_fixtures_ech_ingresos.py [--salida tests/fixtures/ech_ingresos]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html.parser
import io
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import yaml

PAGINA = ("https://www.gub.uy/instituto-nacional-estadistica/datos-y-estadisticas/estadisticas/"
          "series-historicas-ech-ingresos-personas-hogares")
DOMINIOS_OFICIALES = ("https://www5.ine.gub.uy/", "https://www.gub.uy/instituto-nacional-estadistica/")
# Carpeta de la serie vigente (la otra, «Ingresos 2024/», tiene copias viejas y enlaces rotos).
CARPETA = "Ingresos%20de%20las%20personas%20y%20los%20hogares/"
FIXTURES = ["ECHING07", "ECHING09", "ECHINGRESOS2"]
HOJA = "xl/worksheets/sheet1.xml"
ULTIMA_COLUMNA = 8  # H
ULTIMA_FILA = 120
AGENTE = "Mozilla/5.0 (observatorio-uruguay; fixtures)"


class Enlaces(html.parser.HTMLParser):
    """Enlaces a .xlsx de la página, con su texto."""

    def __init__(self):
        super().__init__()
        self.enlaces: list[tuple[str, str]] = []
        self._href: str | None = None
        self._texto: list[str] = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href") or ""
        if tag == "a" and href.lower().endswith(".xlsx"):
            self._href, self._texto = href, []

    def handle_data(self, data):
        if self._href is not None:
            self._texto.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            url = "https:" + self._href if self._href.startswith("//") else self._href
            self.enlaces.append((urllib.parse.quote(url, safe=":/%"), " ".join("".join(self._texto).split())))
            self._href = None


def bajar(url: str) -> bytes:
    if not url.startswith(DOMINIOS_OFICIALES):
        raise SystemExit(f"URL fuera de los dominios oficiales del INE: {url}")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENTE}), timeout=120) as r:
        return r.read()


def numero_columna(letras: str) -> int:
    n = 0
    for ch in letras:
        n = n * 26 + ord(ch) - 64
    return n


def recortar_hoja(xml: str) -> str:
    """Deja solo las celdas de A:H en las filas 1..120 (el resto del XML queda igual)."""

    def fila(m: re.Match) -> str:
        r = int(m.group("r"))
        if r > ULTIMA_FILA:
            return ""
        celdas = re.sub(
            r'<c r="(?P<col>[A-Z]+)\d+"(?:[^>]*/>|[^>]*>.*?</c>)',
            lambda c: c.group(0) if numero_columna(c.group("col")) <= ULTIMA_COLUMNA else "",
            m.group("celdas"), flags=re.S)
        apertura = re.sub(r' spans="[^"]*"', f' spans="1:{ULTIMA_COLUMNA}"', m.group("apertura"))
        return f"{apertura}{celdas}</row>"

    xml = re.sub(r'(?P<apertura><row r="(?P<r>\d+)"[^>]*>)(?P<celdas>.*?)</row>', fila, xml, flags=re.S)
    xml = re.sub(r'<row r="(\d+)"[^>]*/>', lambda m: m.group(0) if int(m.group(1)) <= ULTIMA_FILA else "", xml)
    ultima = max(int(r) for r in re.findall(r'<row r="(\d+)"', xml))
    return re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="A1:H{ultima}"/>', xml, count=1)


def recortar(xlsx: bytes) -> bytes:
    entrada = zipfile.ZipFile(io.BytesIO(xlsx))
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for info in entrada.infolist():
            datos = entrada.read(info.filename)
            if info.filename == HOJA:
                datos = recortar_hoja(datos.decode("utf-8")).encode("utf-8")
            z.writestr(info, datos, compress_type=zipfile.ZIP_DEFLATED)
    return salida.getvalue()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", type=Path, default=Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ech_ingresos")
    args = ap.parse_args(argv)
    args.salida.mkdir(parents=True, exist_ok=True)

    lector = Enlaces()
    lector.feed(bajar(PAGINA).decode("utf-8"))
    hoy = dt.date.today().isoformat()
    registro = []
    for codigo in FIXTURES:
        candidatos = [(u, t) for u, t in lector.enlaces if u.endswith(f"/{CARPETA}{codigo}.xlsx")]
        if not candidatos:
            raise SystemExit(f"La página no enlaza {codigo}.xlsx en la carpeta {CARPETA}")
        url = candidatos[0][0]
        titulo = next((t for _, t in candidatos if t), "")
        original = bajar(url)
        recorte = recortar(original)
        (args.salida / f"{codigo}.xlsx").write_bytes(recorte)
        registro.append({"archivo": f"{codigo}.xlsx", "codigo": codigo, "titulo_enlace": titulo, "pagina": PAGINA,
                         "url": url, "sha256_original": hashlib.sha256(original).hexdigest(),
                         "bytes_original": len(original), "bytes_recorte": len(recorte), "descargado": hoy})
        print(f"{codigo}: {len(original):,} → {len(recorte):,} bytes", file=sys.stderr)

    encabezado = ("# Fixtures de F3.1 (#125). Generado por scripts/crear_fixtures_ech_ingresos.py; no editar a mano.\n"
                  "# Cada archivo es un recorte del original: solo las celdas de A:H en las filas 1–120 de la hoja\n"
                  "# (el original trae ~550.000 celdas vacías con formato). Valores, fórmulas con su valor calculado,\n"
                  "# textos, estilos y notas al pie quedan como en el original.\n")
    (args.salida / "fixtures.yml").write_text(
        encabezado + yaml.safe_dump({"archivos": registro}, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
