"""F2.5b: captura de los informes «Mercado de trabajo por área geográfica de residencia» (INE, ECH).

Cada informe que encuentra el descubrimiento (F2.5a) se baja una sola vez y se guarda sin cambios en
`<crudo>/ech_mt/<año>/<archivo>.html` (año del último mes del trimestre). El registro de capturas,
`<crudo>/ech_mt/capturas.json`, anota de cada uno el período, la página de la publicación, la URL, el
sha256, la fecha de descarga y si es la versión vigente (AC-L1, AC-L3):

- Un informe ya capturado no se vuelve a bajar, salvo con --revisar.
- Si el INE publica otra versión (otra URL para el mismo período, p. ej. `v1_1`) o cambia el contenido de
  la misma URL, se crea una captura nueva y la anterior queda con `vigente = false`. Ningún original se
  pisa ni se borra: el anterior de la misma URL se renombra a `<archivo>.<sha12>.html`.
- Si un original guardado ya no coincide con su sha256, la captura falla: los originales son inmutables.

La carga en `observaciones` es de F2.5c (#58); subir los originales al release `crudos`, de F2.5d (#59).

Uso: python pipeline/ech_captura.py [--crudo datos/crudo] [--revisar] [--limite N]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlsplit

from ech_descubrimiento import Informe, bajar_bytes, bajar_texto, descubrir

from comun.capturas import captura_id

FUENTE_ID = "ine_ech_mercado_trabajo_departamental"
CARPETA = "ech_mt"
REGISTRO = "capturas.json"


class ErrorCaptura(ValueError):
    pass


@dataclass
class ResumenCaptura:
    nuevas: int = 0
    sin_cambios: int = 0

    def como_dict(self) -> dict:
        return {"nuevas": self.nuevas, "sin_cambios": self.sin_cambios}


def nombre_de_archivo(url: str) -> str:
    """Nombre del archivo tal como lo publica el INE (decodificado), si es un .html sin rutas raras."""
    nombre = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    if "/" in nombre or "\\" in nombre or nombre.startswith(".") or not nombre.lower().endswith(".html"):
        raise ErrorCaptura(f"Nombre de archivo inválido para un informe: {nombre!r} ({url})")
    return nombre


def sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def leer_registro(crudo: Path) -> list[dict]:
    path = Path(crudo) / CARPETA / REGISTRO
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["capturas"]


def escribir_registro(crudo: Path, capturas: list[dict]) -> None:
    path = Path(crudo) / CARPETA / REGISTRO
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"fuente_id": FUENTE_ID, "capturas": capturas}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def verificar(crudo: Path, captura: dict) -> None:
    path = Path(crudo) / captura["archivo"]
    if not path.exists():
        raise ErrorCaptura(f"Falta el original de la captura {captura['id']}: {path}")
    if sha256(path.read_bytes()) != captura["sha256"]:
        raise ErrorCaptura(f"El original {path} no coincide con el sha256 de su captura {captura['id']}")


def capturar(informes: list[Informe], crudo: Path, bajar: Callable[[str], bytes], hoy: str | None = None,
             revisar: bool = False) -> ResumenCaptura:
    """Baja (si hace falta) cada informe y actualiza el registro de capturas."""
    crudo, hoy = Path(crudo), hoy or dt.date.today().isoformat()
    registro, resumen = leer_registro(crudo), ResumenCaptura()
    for c in registro:
        verificar(crudo, c)

    for inf in informes:
        de_la_url = [c for c in registro if c["url"] == inf.url]
        if de_la_url and not revisar:
            resumen.sin_cambios += 1
            continue
        datos = bajar(inf.url)
        huella = sha256(datos)
        if any(c["sha256"] == huella for c in de_la_url):
            resumen.sin_cambios += 1
            continue
        if any(c["sha256"] == huella for c in registro):
            raise ErrorCaptura(f"{inf.url} tiene el mismo contenido que otra captura ya registrada")
        nombre = nombre_de_archivo(inf.url)
        destino = Path(CARPETA) / str(inf.periodo.fin.year) / nombre
        for c in de_la_url:  # contenido nuevo en la misma URL: el original anterior se conserva con otro nombre
            if c["archivo"] == destino.as_posix():
                viejo = destino.with_name(f"{Path(nombre).stem}.{c['sha256'][:12]}.html")
                (crudo / destino).rename(crudo / viejo)
                c["archivo"] = viejo.as_posix()
        (crudo / destino).parent.mkdir(parents=True, exist_ok=True)
        (crudo / destino).write_bytes(datos)
        registro.append({"id": captura_id(FUENTE_ID, huella), "fuente_id": FUENTE_ID,
                         "periodo": inf.periodo.etiqueta, "pagina": inf.pagina, "url": inf.url,
                         "archivo": destino.as_posix(), "sha256": huella, "descargado": hoy, "vigente": True})
        resumen.nuevas += 1

    marcar_vigentes(registro, informes)
    registro.sort(key=lambda c: (c["periodo"][-7:], c["descargado"], c["url"]))
    escribir_registro(crudo, registro)
    return resumen


def marcar_vigentes(registro: list[dict], informes: list[Informe]) -> None:
    """Por período, vigente = la última captura de la URL que hoy enlaza la publicación. Los períodos que
    el descubrimiento no trajo esta vez conservan su vigente."""
    actuales = {i.periodo.etiqueta: i.url for i in informes}
    for periodo, url in actuales.items():
        del_periodo = [c for c in registro if c["periodo"] == periodo]
        candidatas = [c for c in del_periodo if c["url"] == url]
        ultima = candidatas[-1] if candidatas else None  # el registro guarda en orden de captura
        for c in del_periodo:
            c["vigente"] = c is ultima


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crudo", type=Path, default=Path("datos/crudo"))
    ap.add_argument("--revisar", action="store_true", help="volver a bajar los ya capturados para ver si cambiaron")
    ap.add_argument("--limite", type=int, help="capturar solo los N informes más recientes")
    args = ap.parse_args(argv)
    descubiertos = descubrir(bajar_texto)
    informes = descubiertos.informes[-args.limite:] if args.limite else descubiertos.informes
    resumen = capturar(informes, args.crudo, bajar_bytes, revisar=args.revisar)
    print(json.dumps({**resumen.como_dict(), "informes": len(informes),
                      "faltantes": descubiertos.faltantes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
