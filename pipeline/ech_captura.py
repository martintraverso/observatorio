"""F2.5b: captura de los informes «Mercado de trabajo por área geográfica de residencia» (INE, ECH).

Cada informe que encuentra el descubrimiento (F2.5a) se baja una sola vez y se guarda sin cambios en
`<crudo>/ech_mt/<año>/<archivo>.html` (año del último mes del trimestre). El registro de capturas,
`<crudo>/ech_mt/capturas.json`, anota de cada uno el período, la página de la publicación, la URL, el
sha256, la fecha de descarga y si es la versión vigente (AC-L1, AC-L3):

- Un informe ya capturado no se vuelve a bajar, salvo con --revisar.
- Si el INE publica otra versión (otra URL para el mismo período, p. ej. `v1_1`) o cambia el contenido de
  la misma URL, se crea una captura nueva y la anterior queda con `vigente = false`. Un original guardado
  nunca se mueve, se pisa ni se borra: si el nombre ya existe, el nuevo se guarda como `<archivo>.<sha12>.html`.
- Si una URL nueva trae el mismo contenido que una captura ya registrada, no se duplica: se informa.
- El registro se guarda después de cada captura nueva, así una corrida cortada no lo deja inconsistente.
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
from dataclasses import dataclass, field
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
    repetidas: list[str] = field(default_factory=list)  # URLs nuevas con el contenido de otra captura

    def como_dict(self) -> dict:
        return {"nuevas": self.nuevas, "sin_cambios": self.sin_cambios, "repetidas": self.repetidas}


def nombre_de_archivo(url: str) -> str:
    """Nombre del archivo tal como lo publica el INE (decodificado), si es un .html sin rutas raras."""
    nombre = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    if ("/" in nombre or "\\" in nombre or nombre.startswith(".") or not nombre.lower().endswith(".html")
            or any(ord(c) < 32 for c in nombre) or len(nombre.encode()) > 200):
        raise ErrorCaptura(f"Nombre de archivo inválido para un informe: {nombre!r} ({url})")
    return nombre


def sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def leer_registro(crudo: Path) -> list[dict]:
    path = Path(crudo) / CARPETA / REGISTRO
    if not path.exists():
        return []
    capturas = json.loads(path.read_text(encoding="utf-8"))["capturas"]
    return sorted(capturas, key=lambda c: c["orden"]) if all("orden" in c for c in capturas) else capturas


def escribir_registro(crudo: Path, capturas: list[dict]) -> None:
    path = Path(crudo) / CARPETA / REGISTRO
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    for i, c in enumerate(capturas):
        c["orden"] = i  # orden de captura (el archivo se lee en este orden)
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

    servida: dict[str, str] = {}  # URL -> sha256 de lo que se bajó en esta corrida
    try:
        for inf in informes:
            de_la_url = [c for c in registro if c["url"] == inf.url]
            if de_la_url and not revisar:
                resumen.sin_cambios += 1
                continue
            datos = bajar(inf.url)
            huella = servida[inf.url] = sha256(datos)
            if any(c["sha256"] == huella for c in de_la_url):
                resumen.sin_cambios += 1
                continue
            if any(c["sha256"] == huella for c in registro):  # el INE movió el mismo archivo a otra URL
                resumen.repetidas.append(inf.url)
                continue
            nombre = nombre_de_archivo(inf.url)
            destino = Path(CARPETA) / str(inf.periodo.fin.year) / nombre
            if (crudo / destino).exists():  # nunca se pisa un original: el nuevo lleva su huella en el nombre
                destino = destino.with_name(f"{Path(nombre).stem}.{huella[:12]}.html")
            if (crudo / destino).exists():
                raise ErrorCaptura(f"Ya existe {destino} y no es de ninguna captura registrada")
            (crudo / destino).parent.mkdir(parents=True, exist_ok=True)
            (crudo / destino).write_bytes(datos)
            registro.append({"id": captura_id(FUENTE_ID, huella), "fuente_id": FUENTE_ID,
                             "periodo": inf.periodo.etiqueta, "pagina": inf.pagina, "url": inf.url,
                             "archivo": destino.as_posix(), "sha256": huella, "descargado": hoy, "vigente": True})
            resumen.nuevas += 1
            escribir_registro(crudo, registro)
    finally:
        marcar_vigentes(registro, informes, servida)
        escribir_registro(crudo, registro)
    return resumen


def marcar_vigentes(registro: list[dict], informes: list[Informe], servida: dict[str, str] | None = None) -> None:
    """Por período, vigente = la captura de la URL que hoy enlaza la publicación: la que coincide con lo que
    se bajó en esta corrida o, si no se bajó, la última capturada. Los períodos que el descubrimiento no trajo
    esta vez conservan su vigente."""
    servida = servida or {}
    for inf in informes:
        del_periodo = [c for c in registro if c["periodo"] == inf.periodo.etiqueta]
        candidatas = [c for c in del_periodo if c["url"] == inf.url]
        bajada = [c for c in candidatas if c["sha256"] == servida.get(inf.url)]
        ultima = (bajada or candidatas or [None])[-1]  # el registro está en orden de captura
        if ultima is None:
            continue  # nada capturado para la URL actual (p. ej. contenido repetido): no se toca
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
