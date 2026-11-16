"""Publica las salidas del pipeline en releases de GitHub sin pisar nunca la última versión buena.

Cada publicación es un release nuevo `datos-AAAAMMDD-HHMMSS`:
  1. se crea como borrador (invisible),
  2. se suben todos los archivos y se verifica que estén,
  3. recién entonces se publica y se marca como "latest".
Si algo falla, se borra el borrador y el "latest" anterior queda como estaba (AC-A3).
La app y los usuarios leen siempre de .../releases/latest/download/<archivo>.

Comandos:
  bajar   Antes de procesar: baja de la última publicación el historial de capturas y las
          salidas, para que el pipeline pueda decir "sin cambios".
  subir   Después de procesar y probar: si el resumen de pipeline/correr.py dice que hay algo
          nuevo, publica un release nuevo; si no, solo actualiza historial y reporte del último.

Uso:
  python scripts/publicar.py bajar [--salida datos/salida]
  python scripts/publicar.py subir --resumen resumen.json [--salida datos/salida]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from gh_cli import ErrorGh, assets, gh, releases  # noqa: E402

from comun.registro import RAIZ  # noqa: E402

PREFIJO = "datos-"
# Lo que se baja de la última publicación para poder decir "sin cambios" (ver SALIDAS de cada script).
PATRONES_BAJAR = ["*.parquet", "observatorio.duckdb", "reporte_validacion.md"]
# Lo que se actualiza en la última publicación cuando no hubo cambios.
SIN_CAMBIOS = ["capturas_historial.parquet", "reporte_validacion.md"]


def ultima_publicacion() -> str | None:
    """Tag del último release de datos publicado (no borrador)."""
    for r in releases():
        if r["tagName"].startswith(PREFIJO) and not r["isDraft"]:
            return r["tagName"]
    return None


def resumen_md(texto: str) -> None:
    print(texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as s:
            s.write(texto + "\n\n")


def bajar(salida: Path) -> int:
    salida.mkdir(parents=True, exist_ok=True)
    tag = ultima_publicacion()
    if tag is None:
        resumen_md("### Publicación anterior\n\nNo hay releases de datos todavía: primera corrida.")
        return 0
    patrones = [x for p in PATRONES_BAJAR for x in ("--pattern", p)]
    gh("release", "download", tag, *patrones, "--dir", str(salida), "--clobber")
    resumen_md(f"### Publicación anterior\n\nBajada de `{tag}` a `{salida}` (historial y salidas).")
    return 0


def archivos_a_publicar(salida: Path, tmp: Path) -> list[Path]:
    web = salida / "web"
    if not (web / "manifest.json").exists():
        raise FileNotFoundError(f"Falta {web}/manifest.json: correr pipeline/web.py")
    shutil.make_archive(str(tmp / "web"), "zip", root_dir=web)
    shutil.copy(web / "manifest.json", tmp / "manifest.json")
    archivos = sorted(salida.glob("*.parquet")) + [salida / "observatorio.duckdb", salida / "reporte_validacion.md"]
    faltan = [p for p in archivos if not p.exists()]
    if faltan:
        raise FileNotFoundError(f"Faltan salidas: {faltan}")
    return [*archivos, tmp / "web.zip", tmp / "manifest.json"]


def notas(resumen: dict, tag: str) -> str:
    filas = [f"| {k} | {v.get('resultado')} | {v.get('observaciones', '')} |" for k, v in resumen["fuentes"].items()]
    corrida = ""
    if os.environ.get("GITHUB_RUN_ID"):
        corrida = (f"Corrida: {os.environ.get('GITHUB_SERVER_URL')}/{os.environ.get('GITHUB_REPOSITORY')}"
                   f"/actions/runs/{os.environ['GITHUB_RUN_ID']} · commit `{os.environ.get('GITHUB_SHA', '')[:7]}`\n\n")
    return "\n".join([
        f"Datos procesados `{tag}`. Fuente de los límites y conteos: INE (uso libre citando la fuente).",
        "", corrida,
        "| Fuente | Resultado | Observaciones |", "|---|---|---:|", *filas, "",
        "Archivos: tablas en Parquet, base `observatorio.duckdb`, `reporte_validacion.md`, "
        "`web.zip` (archivos para la app) y `manifest.json` (tamaño y sha256 de cada archivo de web/).",
    ])


def publicar_nuevo(salida: Path, resumen: dict) -> str:
    tag = PREFIJO + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        archivos = archivos_a_publicar(salida, tmp)
        (tmp / "notas.md").write_text(notas(resumen, tag), encoding="utf-8")
        gh("release", "create", tag, "--draft", "--title", f"Datos {tag[len(PREFIJO):]}",
           "--notes-file", str(tmp / "notas.md"), "--target", os.environ.get("GITHUB_SHA", "main"))
        try:
            gh("release", "upload", tag, *map(str, archivos))
            subidos = set(assets(tag))
            faltan = {p.name for p in archivos} - subidos
            if faltan:
                raise ErrorGh(f"No quedaron subidos: {sorted(faltan)}")
            gh("release", "edit", tag, "--draft=false", "--latest")
        except Exception:
            gh("release", "delete", tag, "--yes", "--cleanup-tag", check=False)  # el latest anterior no se toca
            raise
    return tag


def subir(salida: Path, resumen_path: Path) -> int:
    resumen = json.loads(resumen_path.read_text(encoding="utf-8"))
    if resumen.get("errores"):
        resumen_md(f"### Publicación\n\nNo se publica: hubo errores ({', '.join(resumen['errores'])}).")
        return 1
    if resumen.get("publicar"):
        tag = publicar_nuevo(salida, resumen)
        resumen_md(f"### Publicación\n\nNuevo release `{tag}` publicado y marcado como latest.")
        return 0
    tag = ultima_publicacion()
    if tag is None:
        resumen_md("### Publicación\n\nSin cambios y sin publicación anterior: nada que actualizar.")
        return 0
    gh("release", "upload", tag, *[str(salida / n) for n in SIN_CAMBIOS], "--clobber")
    resumen_md(f"### Publicación\n\nSin cambios en los originales: se actualizó el historial de `{tag}`.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["bajar", "subir"])
    ap.add_argument("--salida", type=Path, default=RAIZ / "datos" / "salida")
    ap.add_argument("--resumen", type=Path, help="JSON de pipeline/correr.py (para 'subir')")
    args = ap.parse_args(argv)
    if args.comando == "bajar":
        return bajar(args.salida)
    if args.resumen is None:
        ap.error("'subir' necesita --resumen")
    return subir(args.salida, args.resumen)


if __name__ == "__main__":
    sys.exit(main())
