"""F4.6 (#169, AC-E25): novedades de los anuarios del MEC en la corrida semanal de datos.

- Lee la página de datos del MEC y los años de anuario que enlaza (solo del sitio oficial, gub.uy).
- Un año posterior al último del registro (`anuarios` de `fuentes/mec_anuario_educacion.yml`): baja su xlsx, sin cambios, a
  `<crudo>/mec_anuario/nuevos/<año>.xlsx` y lo anota en `nuevos.json`. **No se carga**: no entra en `capturas.json`,
  que es lo único que lee la carga, hasta que su mapeo esté en el registro (se inventaría con
  `scripts/inventario_mec.py`).
- Con `--issues`, abre un issue «Nuevo anuario MEC <año>: revisar mapeo» con la etiqueta `necesita-humano`, salvo
  que ya exista uno con ese título (abierto o cerrado): nunca lo repite en las corridas siguientes.
- Un año del registro cuya página enlaza otro xlsx que el del registro (el MEC lo volvió a subir en otra carpeta o con
  otro sufijo): se avisa en el resultado y, con `--issues`, con un issue «Anuario MEC <año> actualizado: revisar URL»,
  una sola vez. Un archivo cambiado en la misma URL lo captura `mec_anuario_captura.py` (otra captura vigente).
- El xlsx de un año nuevo no se sube a «crudos» (no es una captura del registro): el issue lleva su URL y su sha256.

Uso: python pipeline/mec_anuario_novedades.py [--crudo datos/crudo] [--issues]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

from ech_ingresos_captura import es_xlsx
from mec_anuario_captura import bajar as bajar_archivo

from comun.capturas import ahora
from comun.registro import RAIZ, cargar_fuentes

FUENTE_ID = "mec_anuario_educacion"
CARPETA = "mec_anuario"
OFICIAL = "https://www.gub.uy/ministerio-educacion-cultura/"
PAGINA = OFICIAL + "datos-y-estadisticas/datos"
PAGINA_ANIO = PAGINA + "/anuario-estadistico-educacion-{anio}"
AGENTE = "observatorio-uruguay/1.0"


def pedir_oficial(url: str) -> bytes:
    """El contenido de una URL del sitio oficial del MEC (también después de redirecciones)."""
    if not url.startswith(OFICIAL):
        raise ValueError(f"Solo se admite el sitio oficial del MEC: {url}")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENTE}), timeout=180) as r:
        if not r.geturl().startswith(OFICIAL):
            raise ValueError(f"{url} redirige fuera del sitio oficial: {r.geturl()}")
        return r.read()


def anios_en_pagina(html: str) -> list[int]:
    """Los años de anuario que enlaza la página de datos del MEC."""
    return sorted({int(a) for a in re.findall(r"/anuario-estadistico-educacion-(\d{4})\b", html)})


def xlsx_de_pagina(html: str, anio: int) -> str:
    """La URL del xlsx que enlaza la página del anuario (nunca se arma la URL); se espera uno solo."""
    urls = sorted(set(re.findall(r'https://www\.gub\.uy/ministerio-educacion-cultura/sites/[^"]+\.xlsx', html)))
    if len(urls) != 1:
        raise ValueError(f"{anio}: la página enlaza {len(urls)} xlsx; se espera uno")
    return urls[0]


def titulo_issue(anio: int) -> str:
    return f"Nuevo anuario MEC {anio}: revisar mapeo"


def titulo_actualizado(anio: int) -> str:
    return f"Anuario MEC {anio} actualizado: revisar URL"


def cuerpo_actualizado(anio: int, antes: str, ahora_url: str, pagina: str) -> str:
    return (f"La página del anuario {anio} del MEC enlaza otro archivo que el del registro (AC-E25): el MEC lo volvió a "
            f"subir.\n\n- Página: {pagina}\n- En el registro: {antes}\n- En la página: {ahora_url}\n\n"
            "Regenerar el registro con `scripts/inventario_mec.py` (toma la URL de la página) y revisar con el inventario "
            "si cambió algún cuadro. La captura sigue con la URL vieja hasta entonces.\n")


def cuerpo_issue(anio: int, nuevo: dict) -> str:
    return (f"La corrida semanal de datos encontró el anuario {anio} del MEC, que el registro todavía no tiene (AC-E25).\n\n"
            f"- Página: {nuevo['pagina']}\n- Archivo: {nuevo['url']}\n- sha256: `{nuevo['sha256']}`\n\n"
            "Se bajó sin cambios, pero **no se carga** hasta que su mapeo esté en el registro:\n"
            f"1. Sumar {anio} a `ANIOS` de `scripts/inventario_mec.py` y regenerar el inventario y el registro.\n"
            "2. Revisar los cambios de cuadros y de encabezados contra 2024 (D6, D7, `fuentes/mec_anuario/mapeo_manual.yml`).\n"
            "3. Cargar y correr los controles (AC-E17–E22) y el control con el INE (AC-E23).\n")


def issue_existe(titulo: str, gh: Callable[..., str]) -> bool:
    """Si ya hay un issue con ese título exacto, abierto o cerrado."""
    salida = gh("issue", "list", "--state", "all", "--search", f'"{titulo}" in:title', "--json", "title", "--limit", "50")
    return any(i.get("title") == titulo for i in json.loads(salida or "[]"))


def gh_cli(*args: str) -> str:
    import subprocess

    r = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return r.stdout


def novedades(crudo: Path, fuente: dict, pedir: Callable[[str], bytes] = pedir_oficial,
              gh: Callable[..., str] | None = None, bajar: Callable[[str], bytes] = bajar_archivo) -> dict:
    """Busca años nuevos, baja su xlsx a `nuevos/` (sin cargarlos) y años del registro con otra URL en su página; si se
    pasa `gh`, abre el issue de cada uno una sola vez."""
    registrados = {int(a) for a in (fuente.get("anuarios") or {})}
    publicados = anios_en_pagina(pedir(PAGINA).decode("utf-8"))
    carpeta = crudo / CARPETA / "nuevos"
    registro = carpeta / "nuevos.json"
    anotados = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
    resultado = {"publicados": publicados, "nuevos": [], "actualizados": [], "issues": [], "errores": {}}
    # Años del registro: ¿la página enlaza el mismo xlsx? (el MEC cambia la carpeta o el sufijo al volver a subir)
    for anio, f in sorted((int(a), f) for a, f in (fuente.get("anuarios") or {}).items()):
        try:
            pagina = PAGINA_ANIO.format(anio=anio)
            url = xlsx_de_pagina(pedir(pagina).decode("utf-8"), anio)
            if url != f.get("url"):
                resultado["actualizados"].append(anio)
                if gh is not None and not issue_existe(titulo_actualizado(anio), gh):
                    gh("issue", "create", "--title", titulo_actualizado(anio), "--label", "necesita-humano",
                       "--body", cuerpo_actualizado(anio, f.get("url", ""), url, pagina))
                    resultado["issues"].append(anio)
        except Exception as e:
            resultado["errores"][str(anio)] = str(e)
    # Solo años posteriores al último del registro: los anteriores que la página también enlaza (2015–2019, en .rar)
    # esperan su propia decisión (F4.9) y no son «nuevos».
    for anio in [a for a in publicados if a > max(registrados, default=0)]:
        try:
            pagina = PAGINA_ANIO.format(anio=anio)
            url = xlsx_de_pagina(pedir(pagina).decode("utf-8"), anio)
            contenido = bajar(url)  # con tope de tamaño y solo del sitio oficial
            if not es_xlsx(contenido):
                raise ValueError(f"{url} no es un xlsx")
            sha = hashlib.sha256(contenido).hexdigest()
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = carpeta / f"{anio}.xlsx"
            if not destino.exists() or hashlib.sha256(destino.read_bytes()).hexdigest() != sha:
                destino.write_bytes(contenido)  # el original sin cambios; la carga no lo lee
            nuevo = {"pagina": pagina, "url": url, "sha256": sha, "bytes": len(contenido),
                     "visto": anotados.get(str(anio), {}).get("visto") or ahora()}
            anotados[str(anio)] = nuevo
            resultado["nuevos"].append(anio)
            if gh is not None and not issue_existe(titulo_issue(anio), gh):
                gh("issue", "create", "--title", titulo_issue(anio), "--label", "necesita-humano",
                   "--body", cuerpo_issue(anio, nuevo))
                resultado["issues"].append(anio)
        except Exception as e:  # un año que falla no frena los demás (AC-E5)
            resultado["errores"][str(anio)] = str(e)
    if anotados:
        carpeta.mkdir(parents=True, exist_ok=True)
        registro.write_text(json.dumps(anotados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resultado


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crudo", type=Path, default=Path("datos/crudo"))
    ap.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes")
    ap.add_argument("--issues", action="store_true", help="abrir el issue de cada año nuevo (con gh)")
    args = ap.parse_args(argv)
    fuente = cargar_fuentes(args.fuentes)[FUENTE_ID]
    r = novedades(args.crudo, fuente, gh=gh_cli if args.issues else None)
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
