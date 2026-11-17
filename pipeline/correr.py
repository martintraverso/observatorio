"""Reconstruye todo con un comando: cada fuente activa y, si algo cambió, los archivos para la app.

Para cada fuente con estado 'activa' en fuentes/*.yml corre su `script` sobre
`<crudo>/<archivo_original>`. Cada script decide si su original cambió (nuevo /
reprocesado / sin cambios). Si alguna fuente se procesó (o con --web), corre web.py.
No usa la red: los originales tienen que estar en <crudo> (ver scripts/conseguir_originales.py).

Uso:
  python pipeline/correr.py [--crudo datos/crudo] [--salida datos/salida] [--forzar]
      [--resumen resumen.json] [--argumentos FUENTE_ID="--opcion valor"]... [--web] [--sin-pmtiles]

Sale con código != 0 si algún paso falla. El resumen (stdout y --resumen) dice qué pasó
con cada fuente y si hay algo nuevo para publicar.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

from comun.registro import RAIZ, activas, cargar_fuentes

PROCESADO = ("nuevo", "reprocesado")


def correr_fuente(fuente: dict, crudo: Path, salida: Path, forzar: bool, extra: list[str]) -> dict:
    original = crudo / fuente["archivo_original"]
    if not original.exists():
        return {"resultado": "error", "detalle": f"falta el original {original}"}
    cmd = [sys.executable, str(RAIZ / fuente["script"]), str(original), "--salida", str(salida), *extra]
    if forzar:
        cmd.append("--forzar")
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stderr.write(r.stderr)
    lineas = [x for x in r.stdout.strip().splitlines() if x.startswith("{")]
    resumen = json.loads(lineas[-1]) if lineas else {}
    if r.returncode != 0:
        return {**resumen, "resultado": "error", "detalle": f"{fuente['script']} salió con código {r.returncode}"}
    return resumen


def hay_que_armar_web(resultados: dict[str, dict], forzar_web: bool) -> bool:
    """Solo si algo cambió: una corrida 'sin cambios' no tiene nada nuevo para la app."""
    return forzar_web or any(r.get("resultado") in PROCESADO for r in resultados.values())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crudo", type=Path, default=RAIZ / "datos" / "crudo")
    ap.add_argument("--salida", type=Path, default=RAIZ / "datos" / "salida")
    ap.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes")
    ap.add_argument("--forzar", action="store_true", help="reprocesar aunque los originales no hayan cambiado")
    ap.add_argument("--resumen", type=Path, help="escribir el resumen en este JSON")
    ap.add_argument("--argumentos", action="append", default=[], metavar='FUENTE_ID="--opcion valor"',
                    help="argumentos extra para el script de una fuente (p. ej. --esperado del fixture)")
    ap.add_argument("--web", action="store_true", help="armar web/ aunque ninguna fuente haya cambiado")
    ap.add_argument("--sin-pmtiles", action="store_true", help="pasarle --sin-pmtiles a web.py")
    args = ap.parse_args(argv)
    args.salida.mkdir(parents=True, exist_ok=True)

    extra = {}
    for a in args.argumentos:
        fuente_id, _, resto = a.partition("=")
        extra[fuente_id] = shlex.split(resto)

    fuentes = activas(cargar_fuentes(args.fuentes))
    resultados = {f["id"]: correr_fuente(f, args.crudo, args.salida, args.forzar, extra.get(f["id"], []))
                  for f in fuentes}
    errores = [k for k, r in resultados.items() if r.get("resultado") == "error"]

    web = False
    if not errores and hay_que_armar_web(resultados, args.web):
        cmd = [sys.executable, str(RAIZ / "pipeline" / "web.py"), "--salida", str(args.salida)]
        r = subprocess.run(cmd + (["--sin-pmtiles"] if args.sin_pmtiles else []), capture_output=True, text=True)
        sys.stderr.write(r.stderr)
        if r.returncode != 0:
            errores.append("web")
        web = r.returncode == 0

    resumen = {
        "fuentes": resultados,
        "web": web,
        # Hay algo nuevo para publicar si alguna fuente se procesó y todo salió bien.
        "publicar": not errores and any(r.get("resultado") in PROCESADO for r in resultados.values()),
        "errores": errores,
    }
    texto = json.dumps(resumen, ensure_ascii=False)
    print(texto)
    if args.resumen:
        args.resumen.write_text(texto, encoding="utf-8")
    for e in errores:
        print(f"FALLA: {e} — {resultados.get(e, {}).get('detalle', 'ver stderr')}", file=sys.stderr)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
