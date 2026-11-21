"""Baja a datos/crudo/ el original de cada fuente que procesa el pipeline (activas y `cargar: true`).

Las fuentes con `carpeta_original` (varios originales y un registro de capturas) se arman solo desde el
release "crudos" (scripts/crudos_carpeta.py). Los de la ECH de trabajo se capturan aparte (pipeline/ech_captura.py)
y se suben con scripts/subir_crudos.sh; los de ingresos los captura y sube el workflow de datos en cada corrida
(F3.6, #130).


Primero del release "crudos" del repo (la descarga del INE falla a veces). Si no está ahí,
de `url_descarga` de la fuente, y entonces lo agrega a "crudos" para las próximas corridas.
Nunca reemplaza un archivo que ya esté en "crudos": los originales son inmutables. Si la
fuente publica una versión nueva con el mismo nombre, hay que subirla a mano con otro nombre
y actualizar `archivo_original`.

Uso:
  python scripts/conseguir_originales.py [--crudo datos/crudo] [--sin-subir] [--espera 10]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from crudos_carpeta import ErrorCrudos, bajar  # noqa: E402
from gh_cli import ErrorGh, existe_release, gh  # noqa: E402

from comun.huella import sha256_archivo  # noqa: E402
from comun.registro import RAIZ, a_procesar, cargar_fuentes  # noqa: E402

RELEASE = "crudos"
NOTAS = "Archivos originales tal como se descargaron de cada fuente. No se modifican ni se reemplazan."


def de_crudos(nombre: str, crudo: Path) -> bool:
    return gh("release", "download", RELEASE, "--pattern", nombre, "--dir", str(crudo), "--clobber",
              check=False).returncode == 0 and (crudo / nombre).exists()


def de_la_fuente(url: str, destino: Path, intentos: int = 3, espera: float = 10) -> None:
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    for i in range(1, intentos + 1):
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": "observatorio-uruguay/1.0"})
            with urllib.request.urlopen(pedido, timeout=300) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            tmp.replace(destino)
            return
        except OSError as e:
            if i == intentos:
                raise
            print(f"  intento {i} falló ({e}); reintento", file=sys.stderr)
            time.sleep(espera * i)


def a_crudos(path: Path) -> None:
    if not existe_release(RELEASE):
        gh("release", "create", RELEASE, "--title", "Archivos originales", "--notes", NOTAS, "--latest=false")
    gh("release", "upload", RELEASE, str(path))  # sin --clobber: nunca reemplaza


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crudo", type=Path, default=RAIZ / "datos" / "crudo")
    ap.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes")
    ap.add_argument("--sin-subir", action="store_true", help="no agregar a 'crudos' lo bajado de la fuente")
    ap.add_argument("--espera", type=float, default=10, help="segundos entre reintentos de descarga (x intento)")
    args = ap.parse_args(argv)
    args.crudo.mkdir(parents=True, exist_ok=True)

    lineas, fallas = ["### Originales", "", "| Fuente | Archivo | Origen | sha256 |", "|---|---|---|---|"], []
    for f in a_procesar(cargar_fuentes(args.fuentes)):
        if f.get("carpeta_original"):
            carpeta = f["carpeta_original"]
            try:
                n = bajar(args.crudo, carpeta)
                lineas.append(f"| {f['id']} | `{carpeta}/` ({n} informes) | release {RELEASE} | "
                              f"`{sha256_archivo(args.crudo / carpeta / 'capturas.json')[:16]}…` |")
            except (OSError, ErrorGh, ErrorCrudos) as e:
                fallas.append(f"{f['id']}: {e}")
                lineas.append(f"| {f['id']} | `{carpeta}/` | **FALLA** | {e} |")
            continue
        nombre, destino = f["archivo_original"], args.crudo / f["archivo_original"]
        try:
            if destino.exists():
                origen = "ya estaba en datos/crudo"
            elif de_crudos(nombre, args.crudo):
                origen = f"release {RELEASE}"
            else:
                print(f"{nombre}: no está en '{RELEASE}'; lo bajo de {f['url_descarga']}", file=sys.stderr)
                de_la_fuente(f["url_descarga"], destino, espera=args.espera)
                origen = "url_descarga"
                if not args.sin_subir:
                    a_crudos(destino)
                    origen += f" (agregado a {RELEASE})"
            lineas.append(f"| {f['id']} | `{nombre}` | {origen} | `{sha256_archivo(destino)[:16]}…` |")
        except (OSError, ErrorGh) as e:
            fallas.append(f"{f['id']}: {e}")
            lineas.append(f"| {f['id']} | `{nombre}` | **FALLA** | {e} |")

    texto = "\n".join(lineas) + "\n"
    print(texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as s:
            s.write(texto + "\n")
    for falla in fallas:
        print(f"FALLA: {falla}", file=sys.stderr)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
