"""`gh` falso para los tests de releases: guarda los releases en una carpeta (GH_FALSO_DIR).

  <dir>/estado.json   {tag: {"draft": bool, "latest": bool, "createdAt": str}}
  <dir>/<tag>/        assets del release
  <dir>/llamadas.log  una línea por llamada

GH_FALSO_FALLAR=upload hace fallar `release upload` (después de subir el primer archivo).
Implementa solo lo que usan scripts/gh_cli.py, publicar.py y conseguir_originales.py.
"""

import fnmatch
import json
import os
import shutil
import sys
import time
from pathlib import Path

DIR = Path(os.environ["GH_FALSO_DIR"])
ESTADO = DIR / "estado.json"


def leer():
    return json.loads(ESTADO.read_text()) if ESTADO.exists() else {}


def guardar(e):
    ESTADO.write_text(json.dumps(e))


def opcion(args, nombre, defecto=None):
    for i, a in enumerate(args):
        if a == nombre:
            return args[i + 1]
        if a.startswith(nombre + "="):
            return a.split("=", 1)[1]
    return defecto


def multiples(args, nombre):
    return [args[i + 1] for i, a in enumerate(args) if a == nombre]


def error(msg, codigo=1):
    print(msg, file=sys.stderr)
    sys.exit(codigo)


def main(args):
    DIR.mkdir(parents=True, exist_ok=True)
    with open(DIR / "llamadas.log", "a") as log:
        log.write(" ".join(args) + "\n")
    if args[:1] != ["release"]:
        error(f"no implementado: {args}")
    cmd, resto = args[1], args[2:]
    e = leer()

    if cmd == "list":
        print(json.dumps([{"tagName": t, "isDraft": r["draft"], "isLatest": r["latest"], "isPrerelease": False,
                           "createdAt": r["createdAt"]} for t, r in e.items()]))
        return
    tag = resto[0]
    if cmd == "create":
        if tag in e:
            error("release already exists")
        latest = "--draft" not in resto and opcion(resto, "--latest", "true") != "false"
        if latest:
            for r in e.values():
                r["latest"] = False
        e[tag] = {"draft": "--draft" in resto, "latest": latest,
                  "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S") + f".{time.time_ns() % 10**9:09d}Z"}
        (DIR / tag).mkdir(exist_ok=True)
        guardar(e)
        return
    if tag not in e:
        error("release not found")
    carpeta = DIR / tag
    if cmd == "view":
        if opcion(resto, "--json") == "assets":
            print(json.dumps({"assets": [{"name": p.name} for p in sorted(carpeta.iterdir())]}))
        else:
            print(json.dumps({"tagName": tag}))
    elif cmd == "download":
        patrones, destino = multiples(resto, "--pattern"), Path(opcion(resto, "--dir", "."))
        elegidos = [p for p in carpeta.iterdir() if any(fnmatch.fnmatch(p.name, x) for x in patrones)]
        if not elegidos:
            error("no assets match the file pattern")
        destino.mkdir(parents=True, exist_ok=True)
        for p in elegidos:
            shutil.copy(p, destino / p.name)
    elif cmd == "upload":
        archivos = [a for a in resto[1:] if not a.startswith("--")]
        for i, a in enumerate(archivos):
            if os.environ.get("GH_FALSO_FALLAR") == "upload" and i == 1:
                error("upload failed: network error")
            if (carpeta / Path(a).name).exists() and "--clobber" not in resto:
                error(f"asset {Path(a).name} already exists")
            shutil.copy(a, carpeta / Path(a).name)
    elif cmd == "edit":
        if opcion(resto, "--draft") == "false":
            e[tag]["draft"] = False
        if "--latest" in resto:
            for r in e.values():
                r["latest"] = False
            e[tag]["latest"] = True
        guardar(e)
    elif cmd == "delete":
        del e[tag]
        shutil.rmtree(carpeta)
        guardar(e)
    else:
        error(f"no implementado: {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
