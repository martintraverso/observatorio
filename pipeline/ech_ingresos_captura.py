"""F3.4a (#137): captura de las planillas de ingresos del INE (AC-I4 parte local, AC-I5 y AC-I6 parte de captura).

Baja cada planilla del conjunto mínimo (las de `archivos` del registro que tienen `indicador`) desde la URL que
dice el registro y la guarda sin cambios en `<crudo>/ech_ingresos/<código>.xlsx`. El registro de capturas,
`<crudo>/ech_ingresos/capturas.json`, anota de cada una el código, la URL, el sha256, la fecha de descarga y si es
la versión vigente, como `ech_captura.py` (F2.5b):

- Si el archivo no cambió (mismo sha256 que la captura vigente de ese código), no se vuelve a guardar.
- Si cambió, es una captura nueva y la anterior queda con `vigente = false`. Un original guardado nunca se pisa
  ni se borra: si el nombre ya existe, el nuevo se guarda como `<código>.<sha12>.xlsx`.
- Si una planilla da error (HTTP 404, contenido que no es xlsx), queda en `ultima_corrida.errores` del registro
  y las demás se capturan igual (AC-I5). El reporte lo arma la carga (F3.4b).
- Si un original guardado ya no coincide con su sha256, la captura falla: los originales son inmutables.

Uso: python pipeline/ech_ingresos_captura.py [--crudo datos/crudo] [--fuentes fuentes/]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NamedTuple

from ech_descubrimiento import DOMINIOS_OFICIALES, bajar_bytes

from comun.capturas import captura_id
from comun.registro import RAIZ, cargar_fuentes

FUENTE_ID = "ine_ech_ingresos_series"
CARPETA = "ech_ingresos"
REGISTRO = "capturas.json"


class ErrorCaptura(ValueError):
    pass


class Planilla(NamedTuple):
    codigo: str
    url: str


@dataclass
class ResumenCaptura:
    nuevas: int = 0
    sin_cambios: int = 0
    errores: list[dict] = field(default_factory=list)  # {codigo, url, error}

    def como_dict(self) -> dict:
        return {"nuevas": self.nuevas, "sin_cambios": self.sin_cambios, "errores": self.errores}


def planillas(fuente: dict) -> list[Planilla]:
    """Las planillas del conjunto mínimo (con indicador), en el orden del registro."""
    return [Planilla(a["codigo"], a["url"]) for a in fuente["archivos"] if a.get("indicador")]


def sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _leer(crudo: Path) -> dict:
    path = Path(crudo) / CARPETA / REGISTRO
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"capturas": []}


def leer_registro(crudo: Path) -> list[dict]:
    """Las capturas, en orden de captura."""
    return _leer(crudo)["capturas"]


def escribir_registro(crudo: Path, capturas: list[dict], ultima_corrida: dict | None) -> None:
    path = Path(crudo) / CARPETA / REGISTRO
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    contenido = {"fuente_id": FUENTE_ID, "capturas": capturas}
    if ultima_corrida is not None:
        contenido["ultima_corrida"] = ultima_corrida
    tmp.write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def verificar(crudo: Path, captura: dict) -> None:
    path = Path(crudo) / captura["archivo"]
    if not path.exists():
        raise ErrorCaptura(f"Falta el original de la captura {captura['id']}: {path}")
    if sha256(path.read_bytes()) != captura["sha256"]:
        raise ErrorCaptura(f"El original {path} no coincide con el sha256 de su captura {captura['id']}")


def es_xlsx(datos: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            return "xl/workbook.xml" in z.namelist()
    except zipfile.BadZipFile:
        return False


def capturar(lista: list[Planilla], crudo: Path, bajar: Callable[[str], bytes], hoy: str | None = None) -> ResumenCaptura:
    """Baja cada planilla y actualiza el registro de capturas."""
    crudo, hoy = Path(crudo), hoy or dt.date.today().isoformat()
    fuera = [pl.url for pl in lista if not pl.url.startswith(DOMINIOS_OFICIALES)]
    if fuera:
        raise ErrorCaptura(f"Solo se admiten URLs oficiales del INE: {fuera}")
    registro, resumen = leer_registro(crudo), ResumenCaptura()
    for c in registro:
        verificar(crudo, c)

    try:
        for pl in lista:
            try:
                datos = bajar(pl.url)
            except Exception as e:  # noqa: BLE001 — cualquier falla de la descarga se informa y se sigue (AC-I5)
                resumen.errores.append({"codigo": pl.codigo, "url": pl.url, "error": f"{type(e).__name__}: {e}"})
                continue
            if not es_xlsx(datos):
                resumen.errores.append({"codigo": pl.codigo, "url": pl.url,
                                        "error": f"el contenido no es una planilla xlsx ({len(datos)} bytes)"})
                continue
            huella = sha256(datos)
            del_codigo = [c for c in registro if c["codigo"] == pl.codigo]
            vigente = next((c for c in reversed(del_codigo) if c["vigente"]), None)
            if vigente and vigente["sha256"] == huella:
                resumen.sin_cambios += 1
                continue
            if any(c["sha256"] == huella for c in registro):
                otra = next(c for c in registro if c["sha256"] == huella)
                raise ErrorCaptura(f"{pl.codigo}: el contenido es el de una captura anterior ({otra['codigo']}, "
                                   f"{otra['descargado']}); revisar a mano antes de cambiar la vigente")
            destino = Path(CARPETA) / f"{pl.codigo}.xlsx"
            if (crudo / destino).exists():  # nunca se pisa un original
                destino = destino.with_name(f"{pl.codigo}.{huella[:12]}.xlsx")
            if (crudo / destino).exists():
                raise ErrorCaptura(f"Ya existe {destino} y no es de ninguna captura registrada")
            (crudo / destino).parent.mkdir(parents=True, exist_ok=True)
            (crudo / destino).write_bytes(datos)
            for c in del_codigo:
                c["vigente"] = False
            registro.append({"id": captura_id(FUENTE_ID, huella), "fuente_id": FUENTE_ID, "codigo": pl.codigo,
                             "url": pl.url, "archivo": destino.as_posix(), "sha256": huella, "descargado": hoy,
                             "vigente": True})
            resumen.nuevas += 1
            escribir_registro(crudo, registro, None)  # así una corrida cortada no pierde lo ya guardado
    finally:
        escribir_registro(crudo, registro, {"fecha": hoy, "errores": resumen.errores})
    return resumen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crudo", type=Path, default=Path("datos/crudo"))
    ap.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes")
    args = ap.parse_args(argv)
    lista = planillas(cargar_fuentes(args.fuentes)[FUENTE_ID])
    resumen = capturar(lista, args.crudo, bajar_bytes)
    print(json.dumps({**resumen.como_dict(), "planillas": len(lista)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
