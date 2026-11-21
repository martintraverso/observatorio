"""Originales de las fuentes con varios archivos (p. ej. datos/crudo/ech_mt/) en el release "crudos".

Un release no tiene carpetas. Por eso cada original se sube como `<carpeta>-<sha12><extensión>` (`.html` en
ech_mt, `.xlsx` en ech_ingresos: la del archivo de la captura), y el registro de
capturas como `<carpeta>-capturas-<NNNN>-<sha12>.json`, donde NNNN es la versión del registro: crece siempre
(el máximo entre la versión anterior + 1 y la cantidad de capturas, así en ech_mt, cuyo registro solo crece, sigue
siendo la cantidad de capturas). El de NNNN mayor es el último. Nada se reemplaza: cada versión es un asset nuevo.
Un registro que solo cambió en `ultima_corrida` (ech_ingresos la reescribe en cada captura) no se vuelve a subir.

  subir: sube los originales y el registro que todavía no están en "crudos".
  bajar: arma <crudo>/<carpeta>/ desde "crudos" con el último registro y verifica el sha256 de cada original.
         No usa la red del INE: el workflow nunca depende de que el sitio de la fuente esté arriba.

Uso: python scripts/crudos_carpeta.py subir|bajar [--crudo datos/crudo] [--carpeta ech_mt]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from gh_cli import ErrorGh, assets, existe_release, gh  # noqa: E402

from comun.registro import RAIZ  # noqa: E402

RELEASE = "crudos"
NOTAS = "Archivos originales tal como se descargaron de cada fuente. No se modifican ni se reemplazan."
REGISTRO = "capturas.json"


class ErrorCrudos(RuntimeError):
    pass


def sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def asset_original(carpeta: str, sha: str, sufijo: str = ".html") -> str:
    return f"{carpeta}-{sha[:12]}{sufijo}"


def sufijo(captura: dict) -> str:
    """Extensión del original de la captura (`.html`, `.xlsx`)."""
    return Path(captura["archivo"]).suffix or ".html"


def asset_registro(carpeta: str, datos: bytes, anterior: str | None = None) -> str:
    """Nombre del registro: versión = max(versión anterior + 1, cantidad de capturas)."""
    n = len(json.loads(datos)["capturas"])
    if anterior is not None:
        n = max(n, int(anterior.rsplit("-", 2)[1]) + 1)
    return f"{carpeta}-capturas-{n:04d}-{sha256(datos)[:12]}.json"


def contenido(datos: bytes) -> dict:
    """El registro sin `ultima_corrida`: lo que cambia cuando cambian las capturas o cuál es la vigente."""
    return {k: v for k, v in json.loads(datos).items() if k != "ultima_corrida"}


def ultimo_registro(nombres: list[str], carpeta: str) -> str | None:
    patron = re.compile(rf"^{re.escape(carpeta)}-capturas-(\d{{4}})-[0-9a-f]{{12}}\.json$")
    regs = sorted((int(m.group(1)), n) for n in nombres if (m := patron.match(n)))
    if not regs:
        return None
    if len(regs) > 1 and regs[-1][0] == regs[-2][0]:
        raise ErrorCrudos(f"Hay dos registros con {regs[-1][0]} capturas: {regs[-2][1]}, {regs[-1][1]}")
    return regs[-1][1]


def subir(crudo: Path, carpeta: str) -> list[str]:
    registro_path = crudo / carpeta / REGISTRO
    datos = registro_path.read_bytes()
    capturas = json.loads(datos)["capturas"]
    if not existe_release(RELEASE):
        gh("release", "create", RELEASE, "--title", "Archivos originales", "--notes", NOTAS, "--latest=false")
    ya = set(assets(RELEASE))
    subidos = []
    with tempfile.TemporaryDirectory() as tmp:
        for c in capturas:
            nombre = asset_original(carpeta, c["sha256"], sufijo(c))
            if nombre in ya:
                continue
            original = crudo / c["archivo"]
            if sha256(original.read_bytes()) != c["sha256"]:
                raise ErrorCrudos(f"{original} no coincide con el sha256 de su captura {c['id']}")
            shutil.copy(original, Path(tmp) / nombre)
            gh("release", "upload", RELEASE, str(Path(tmp) / nombre))  # sin --clobber: nunca reemplaza
            subidos.append(nombre)
        anterior = ultimo_registro(sorted(ya), carpeta)
        if anterior is not None and contenido(bajar_asset(anterior, Path(tmp))) == contenido(datos):
            return subidos  # el registro de crudos ya tiene estas capturas y vigentes
        nombre = asset_registro(carpeta, datos, anterior)
        if nombre not in ya:
            (Path(tmp) / nombre).write_bytes(datos)
            gh("release", "upload", RELEASE, str(Path(tmp) / nombre))
            subidos.append(nombre)
    return subidos


def bajar_asset(nombre: str, destino: Path) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        gh("release", "download", RELEASE, "--pattern", nombre, "--dir", tmp)
        return (Path(tmp) / nombre).read_bytes()


def bajar(crudo: Path, carpeta: str) -> int:
    """Deja <crudo>/<carpeta>/ completa; devuelve la cantidad de capturas."""
    d = crudo / carpeta
    if (d / REGISTRO).exists():
        datos = (d / REGISTRO).read_bytes()  # ya estaba (p. ej. corrida local): se completa lo que falte
    else:
        nombre = ultimo_registro(assets(RELEASE), carpeta)
        if nombre is None:
            raise ErrorCrudos(f"No hay registro de {carpeta} en el release {RELEASE}")
        datos = bajar_asset(nombre, d)
        if sha256(datos)[:12] != nombre.rsplit("-", 1)[1][:12]:
            raise ErrorCrudos(f"{nombre} no coincide con su sha256")
    capturas = json.loads(datos)["capturas"]
    for c in capturas:
        destino = crudo / c["archivo"]
        if destino.exists() and sha256(destino.read_bytes()) == c["sha256"]:
            continue
        nombre = asset_original(carpeta, c["sha256"], sufijo(c))
        contenido = bajar_asset(nombre, destino)
        if sha256(contenido) != c["sha256"]:
            raise ErrorCrudos(f"{nombre} no coincide con el sha256 de la captura {c['id']}")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
    d.mkdir(parents=True, exist_ok=True)
    (d / REGISTRO).write_bytes(datos)
    return len(capturas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("accion", choices=["subir", "bajar"])
    ap.add_argument("--crudo", type=Path, default=RAIZ / "datos" / "crudo")
    ap.add_argument("--carpeta", default="ech_mt")
    args = ap.parse_args(argv)
    try:
        if args.accion == "subir":
            subidos = subir(args.crudo, args.carpeta)
            print(json.dumps({"subidos": len(subidos), "archivos": subidos}, ensure_ascii=False))
        else:
            print(json.dumps({"capturas": bajar(args.crudo, args.carpeta)}))
    except (ErrorCrudos, ErrorGh, OSError) as e:
        print(f"FALLA: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
