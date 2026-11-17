"""Fixtures de los informes «Mercado de trabajo por área geográfica de residencia» (INE, ECH) — F2.1.

Baja tres informes de épocas distintas (solo de dominios oficiales del INE), guarda en
tests/fixtures/ech_mt/ un recorte de cada uno y anota en fixtures.yml la URL, la página de la
publicación, el sha256 y el tamaño del original.

Recorte: se quitan los <script> (gráficos plotly embebidos como JSON, ~20 MB), los <style> (CSS
embebido, ~400 kB) y las imágenes en data: URIs. Las tablas y el texto del informe quedan tal cual.
Los originales completos se capturan en F2.5 (datos/crudo/ech_mt/ y release crudos).

Uso: python scripts/crear_fixtures_ech.py [--salida tests/fixtures/ech_mt]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

import yaml

DOMINIOS_OFICIALES = ("https://www5.ine.gub.uy/", "https://www.gub.uy/instituto-nacional-estadistica/")
PUBLICACIONES = "https://www.gub.uy/instituto-nacional-estadistica/comunicacion/publicaciones/"

# periodo_fin (último mes del trimestre móvil), página de la publicación y URL del HTML (tomada de esa página).
INFORMES = [
    ("2022-02", PUBLICACIONES + "mercado-trabajo-area-geografica-residencia-ech-febrero-2022",
     "https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/HTML/ECH/Empleo/"
     "Mercado%20Laboral%20por%20%C3%81rea%20Geogr%C3%A1fica%20de%20Residencia%20-%20feb%202022.html"),
    ("2024-09", PUBLICACIONES + "mercado-trabajo-area-geografica-residencia-ech-julio-setiembre-2024",
     "https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/HTML/ECH/Mercado%20de%20trabajo%20por%20"
     "%C3%A1rea%20geogr%C3%A1fica/2024/Informe_departamental-Julio-Setiembre2024.html"),
    ("2026-09", PUBLICACIONES + "mercado-trabajo-area-geografica-residencia-ech-julio-setiembre-2026",
     "https://www5.ine.gub.uy/documents/Demograf%C3%ADayEESS/HTML/ECH/Mercado%20de%20trabajo%20por%20"
     "%C3%A1rea%20geogr%C3%A1fica/2026/Mercado_trabajo_IN_SOC_MTR_2026_M_09-_v1_0.html"),
]

SCRIPT = re.compile(rb"<script\b[^>]*>.*?</script\s*>", re.S | re.I)
STYLE = re.compile(rb"<style\b[^>]*>.*?</style\s*>", re.S | re.I)
DATA_URI = re.compile(rb"""(src|href)\s*=\s*(["'])data:[^"']*\2""", re.I)


def bajar(url: str) -> bytes:
    if not url.startswith(DOMINIOS_OFICIALES):
        raise ValueError(f"Solo se admiten sitios oficiales del INE: {url}")
    pedido = urllib.request.Request(url, headers={"User-Agent": "observatorio-uruguay/1.0"})
    with urllib.request.urlopen(pedido, timeout=180) as r:
        return r.read()


def recortar(html: bytes) -> bytes:
    html = SCRIPT.sub(b"<!-- script quitado del fixture -->", html)
    html = STYLE.sub(b"<!-- estilo quitado del fixture -->", html)
    return DATA_URI.sub(rb'\1=\2\2', html)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=Path("tests/fixtures/ech_mt"))
    args = ap.parse_args(argv)
    args.salida.mkdir(parents=True, exist_ok=True)

    hoy = dt.date.today().isoformat()
    informes = []
    for fin, pagina, url in INFORMES:
        original = bajar(url)
        archivo = f"ech_mt_{fin.replace('-', '_')}.html"
        (args.salida / archivo).write_bytes(recortar(original))
        informes.append({"archivo": archivo, "periodo_fin": fin, "pagina": pagina, "url": url,
                         "sha256_original": hashlib.sha256(original).hexdigest(), "bytes_original": len(original),
                         "descargado": hoy})
        print(f"{archivo}: {len(original) / 1e6:.1f} MB -> {(args.salida / archivo).stat().st_size / 1e3:.0f} kB")

    encabezado = ("# Fixtures de F2.1 (#40). Generado por scripts/crear_fixtures_ech.py; no editar a mano.\n"
                  "# Cada archivo es un recorte del original (sin <script>, <style> ni imágenes data:); tablas y texto intactos.\n")
    (args.salida / "fixtures.yml").write_text(
        encabezado + yaml.safe_dump({"informes": informes}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
