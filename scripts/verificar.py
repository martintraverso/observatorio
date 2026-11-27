"""Verificación local: corre solo los pasos que tocan los archivos cambiados.

Compara la rama con su base (por defecto `origin/main`, más lo que no está commiteado) y arma el plan:

  python   ruff + pytest con el fixture (como CI)        pipeline/, tests/, fuentes/, scripts/, pyproject, requirements
  datos    pipeline/web.py + OBS_DATOS=completo pytest   pipeline/, fuentes/
  app      check + vitest + build + Playwright           app/, o pipeline/web.py (cambia lo que lee la app)

Solo docs u otros archivos: no corre nada. `--todo` corre todo.

`web.py` rehace `datos/salida/web` desde los Parquet que ya están en `datos/salida/`: si cambiaste el cargador de
una fuente, corré antes su script (o `pipeline/correr.py --forzar`) para que los Parquet tengan el código nuevo.
En un worktree, `datos/salida` suele ser un enlace a la del repo principal: `web.py` la reescribe.

Uso:
  python scripts/verificar.py [--base origin/main] [--todo] [--plan] [--sin-e2e] [--logs CARPETA]

Sale con código 1 si algún paso falla. La salida de cada paso queda en --logs (por defecto, una carpeta temporal).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PY = sys.executable

PYTHON = ("pipeline/", "tests/", "fuentes/", "scripts/", "pyproject.toml", "requirements")
DATOS = ("pipeline/", "fuentes/")
APP = ("app/", "pipeline/web.py")


@dataclass
class Paso:
    nombre: str
    cmd: list[str]
    cwd: Path = RAIZ
    env: dict[str, str] = field(default_factory=dict)
    necesita: str | None = None  # si ese paso falló, este no corre


def grupos(archivos: list[str]) -> set[str]:
    """Qué grupos de pasos tocan los archivos cambiados."""
    g = set()
    for a in archivos:
        if a.startswith(PYTHON):
            g.add("python")
        if a.startswith(DATOS):
            g.add("datos")
        if a.startswith(APP):
            g.add("app")
    return g


def plan(g: set[str], e2e: bool = True) -> list[Paso]:
    web = RAIZ / "datos" / "salida" / "web"
    pasos = []
    if "python" in g:
        pasos += [Paso("ruff", [PY, "-m", "ruff", "check", "."]),
                  Paso("pytest (fixture)", [PY, "-m", "pytest", "-q"], env={"OBS_DATOS": "fixture"})]
    if "datos" in g:
        pasos += [Paso("web.py", [PY, "pipeline/web.py"]),
                  Paso("pytest (completo)", [PY, "-m", "pytest", "-q"], env={"OBS_DATOS": "completo"},
                       necesita="web.py")]
    if "app" in g:
        app = RAIZ / "app"
        datos = {"DATOS_WEB": str(web)}
        necesita = "web.py" if "datos" in g else None
        pasos += [Paso("app: check", ["npm", "run", "check"], app, datos, necesita),
                  Paso("app: vitest", ["npm", "run", "test:unit"], app, datos, necesita),
                  Paso("app: build", ["npm", "run", "build"], app, {**datos, "BASE_PATH": "/observatorio"}, necesita)]
        if e2e:
            pasos.append(Paso("app: e2e", ["npx", "playwright", "test", "--reporter=line"], app, datos, "app: build"))
    return pasos


def cambiados(base: str) -> list[str]:
    def git(*args):
        r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True)
        return r.stdout.splitlines()

    commits = git("diff", "--name-only", f"{base}...HEAD")
    sin_commit = [linea[3:].split(" -> ")[-1] for linea in git("status", "--porcelain", "--untracked-files=all")]
    return sorted(set(commits) | set(sin_commit))


def correr(pasos: list[Paso], logs: Path) -> list[tuple[str, str, float]]:
    resultados, fallados = [], set()
    for i, p in enumerate(pasos, 1):
        if p.necesita in fallados:
            resultados.append((p.nombre, "SALTEADO", 0.0))
            fallados.add(p.nombre)
            print(f"[{i}/{len(pasos)}] {p.nombre}: salteado ({p.necesita} falló)", flush=True)
            continue
        log = logs / f"{i:02d}-{p.nombre.replace(' ', '_').replace(':', '').replace('(', '').replace(')', '')}.log"
        print(f"[{i}/{len(pasos)}] {p.nombre} …", end=" ", flush=True)
        t = time.monotonic()
        with open(log, "w", encoding="utf-8") as f:
            r = subprocess.run(p.cmd, cwd=p.cwd, env={**os.environ, **p.env}, stdout=f, stderr=subprocess.STDOUT)
        dur = time.monotonic() - t
        estado = "OK" if r.returncode == 0 else "FALLA"
        if estado == "FALLA":
            fallados.add(p.nombre)
        resultados.append((p.nombre, estado, dur))
        print(f"{estado} ({dur:.0f} s)", flush=True)
        if estado == "FALLA":
            cola = log.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
            print("\n".join("    " + x for x in cola), f"\n    (completo en {log})", sep="\n", flush=True)
    return resultados


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main", help="contra qué comparar (por defecto origin/main)")
    ap.add_argument("--todo", action="store_true", help="correr todos los pasos, sin mirar qué cambió")
    ap.add_argument("--plan", action="store_true", help="solo mostrar qué correría")
    ap.add_argument("--sin-e2e", action="store_true", help="no correr Playwright")
    ap.add_argument("--logs", type=Path, help="carpeta para la salida de cada paso")
    args = ap.parse_args(argv)

    archivos = [] if args.todo else cambiados(args.base)
    g = {"python", "datos", "app"} if args.todo else grupos(archivos)
    pasos = plan(g, e2e=not args.sin_e2e)
    if not args.todo:
        print(f"{len(archivos)} archivos cambiados respecto de {args.base}; grupos: {', '.join(sorted(g)) or 'ninguno'}")
    if "datos" in g and (RAIZ / "datos" / "salida").is_symlink():
        print(f"Aviso: datos/salida es un enlace a {(RAIZ / 'datos' / 'salida').resolve()}; web.py la reescribe.")
    if not pasos:
        print("Nada que correr (solo docs u otros archivos).")
        return 0
    for p in pasos:
        print(f"  - {p.nombre}: {' '.join(p.cmd)}" + (f"  [en {p.cwd.relative_to(RAIZ)}]" if p.cwd != RAIZ else ""))
    if args.plan:
        return 0

    logs = args.logs or Path(tempfile.mkdtemp(prefix="verificar-"))
    logs.mkdir(parents=True, exist_ok=True)
    resultados = correr(pasos, logs)
    print("\nResumen:")
    for nombre, estado, dur in resultados:
        print(f"  {estado:9} {nombre} ({dur:.0f} s)")
    print(f"Salida de cada paso: {logs}")
    return 0 if all(e == "OK" for _, e, _ in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
