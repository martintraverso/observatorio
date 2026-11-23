"""F4.4 (#167): captura de los anuarios del MEC (AC-E4, AC-E5, AC-E6 parte de captura).

Baja el xlsx de cada año del registro (`anuarios` de `fuentes/mec_anuario_educacion.yml`, URL tomada de la página
del anuario en F4.1) y lo guarda sin cambios en `<crudo>/mec_anuario/<año>.xlsx`, con su registro de capturas
`<crudo>/mec_anuario/capturas.json`. Usa la misma captura que las planillas de ingresos (F3.4a): un archivo sin
cambios no se vuelve a guardar; uno cambiado es una captura nueva `vigente`; un original guardado nunca se pisa;
un año que da error queda en `ultima_corrida.errores` y los demás se capturan igual (AC-E5).

Uso: python pipeline/mec_anuario_captura.py [--crudo datos/crudo] [--fuentes fuentes/]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from ech_ingresos_captura import Planilla, capturar

from comun.registro import RAIZ, cargar_fuentes

FUENTE_ID = "mec_anuario_educacion"
CARPETA = "mec_anuario"
OFICIAL = ("https://www.gub.uy/ministerio-educacion-cultura/",)
MAX_BYTES = 50_000_000  # los anuarios pesan ~2 MB


def anuarios(fuente: dict) -> list[Planilla]:
    """Un archivo por año, en orden: el código es el año."""
    return [Planilla(str(a), f["url"]) for a, f in sorted(fuente["anuarios"].items())]


def bajar(url: str, timeout: int = 180) -> bytes:
    """Trae el archivo sin modificarlo, solo del sitio oficial del MEC (también después de redirecciones)."""
    if not url.startswith(OFICIAL):
        raise ValueError(f"Solo se admite el sitio oficial del MEC: {url}")
    pedido = urllib.request.Request(url, headers={"User-Agent": "observatorio-uruguay/1.0"})
    with urllib.request.urlopen(pedido, timeout=timeout) as r:
        if not r.geturl().startswith(OFICIAL):
            raise ValueError(f"La descarga terminó fuera del sitio oficial del MEC: {r.geturl()}")
        datos = r.read(MAX_BYTES + 1)
    if len(datos) > MAX_BYTES:
        raise ValueError(f"{url} pesa más de {MAX_BYTES // 1_000_000} MB")
    return datos


def capturar_anuarios(crudo: Path, fuente: dict, bajar_=bajar, hoy: str | None = None):
    return capturar(anuarios(fuente), crudo, bajar_, hoy, carpeta=CARPETA, fuente_id=FUENTE_ID, dominios=OFICIAL)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crudo", type=Path, default=Path("datos/crudo"))
    ap.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes")
    args = ap.parse_args(argv)
    fuente = cargar_fuentes(args.fuentes)[FUENTE_ID]
    resumen = capturar_anuarios(args.crudo, fuente)
    print(json.dumps({**resumen.como_dict(), "anuarios": len(fuente["anuarios"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
