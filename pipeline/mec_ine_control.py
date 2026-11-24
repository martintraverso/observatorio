"""F4.5b (#189): control cruzado de los datos de educación (MEC) con el Anuario Estadístico Nacional del INE
(cap. 3.1 «Educación e investigación»), AC-E23. Solo advertencias: los valores del INE **nunca se cargan**.

- `tablas_del_capitulo(html)`: los enlaces 3.1.x de la página del capítulo (la URL se toma de la página, nunca se
  arma). `bajar(url)` solo acepta los sitios oficiales del INE.
- `leer_tabla(xls)`: una tabla del INE (.xls, con xlrd) en formato largo: año, territorio, columna (ruta del
  encabezado, p. ej. «General/Pública/Mujeres») y valor. Filas por año («2023», «2024») y por territorio («Total
  País» → país, «Montevideo», «Resto País» → Interior, los 18 departamentos).
- `comparar(ine, obs)`: para cada columna del INE, el indicador del MEC que es la misma medida: el mismo valor del
  país en todos los años que publica el INE (los porcentajes, redondeados como el INE). Si lo hay, compara cada
  territorio y año y lista las diferencias; si no, la columna queda como «sin medida igual en el MEC».

Las tablas se guardan sin cambios en `<crudo>/mec_anuario/control_ine/` con su `control_ine.json` (URL, sha256,
fecha), los baja `pipeline/mec_anuario_captura.py --control-ine`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

import mec_anuario as mec
import pandas as pd

PAGINA = ("https://www.gub.uy/instituto-nacional-estadistica/comunicacion/publicaciones/"
          "anuario-estadistico-nacional-2025-vol-102/capitulo-3-aspectos-sociales")
OFICIAL = ("https://www5.ine.gub.uy/", "https://www.gub.uy/instituto-nacional-estadistica/")
TABLAS = [f"3.1.{n}" for n in range(2, 13)]  # las que repiten cuadros del MEC por departamento
CARPETA = Path("mec_anuario") / "control_ine"


def bajar(url: str, timeout: int = 120) -> bytes:
    if not url.startswith(OFICIAL):
        raise ValueError(f"Solo se admiten sitios oficiales del INE: {url}")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "observatorio-uruguay/1.0"}),
                                timeout=timeout) as r:
        if not r.geturl().startswith(OFICIAL):
            raise ValueError(f"La descarga terminó fuera de los sitios oficiales del INE: {r.geturl()}")
        return r.read()


def tablas_del_capitulo(pagina: str) -> dict[str, str]:
    """{«3.1.6»: url} de los enlaces de la página del capítulo."""
    salida = {}
    for url in re.findall(r'href="([^"]+/(3\.1\.\d+)ok\.xlsx?)"', pagina):
        salida.setdefault(url[1], urllib.parse.quote(html.unescape(url[0]), safe=":/%"))  # tildes y espacios
    return salida


def capturar(crudo: Path, bajar_=bajar, hoy: str | None = None) -> dict:
    """Baja las tablas 3.1.2–3.1.12 y las guarda sin cambios, con su manifiesto. Un error se anota y sigue."""
    destino = Path(crudo) / CARPETA
    destino.mkdir(parents=True, exist_ok=True)
    enlaces = tablas_del_capitulo(bajar_(PAGINA).decode("utf-8"))
    manifiesto = {"pagina": PAGINA, "fecha": hoy or dt.date.today().isoformat(), "tablas": {}, "errores": []}
    for t in TABLAS:
        if t not in enlaces:
            manifiesto["errores"].append({"tabla": t, "error": "la página no la enlaza"})
            continue
        try:
            datos = bajar_(enlaces[t])
        except Exception as e:  # noqa: BLE001 — se anota y siguen las demás
            manifiesto["errores"].append({"tabla": t, "error": f"{type(e).__name__}: {e}"})
            continue
        nombre = t + Path(enlaces[t]).suffix
        (destino / nombre).write_bytes(datos)
        manifiesto["tablas"][t] = {"url": enlaces[t], "archivo": nombre, "sha256": hashlib.sha256(datos).hexdigest()}
    (destino / "control_ine.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifiesto


def _territorio(rotulo: str) -> str | None:
    p = mec.plegar(rotulo)
    if p in ("total pais", "total"):
        return mec.PAIS
    if p in ("resto pais", "resto del pais", "interior"):
        return mec.INTERIOR
    return mec.territorio_de_fila(rotulo)


def leer_tabla(xls: bytes, tabla: str) -> pd.DataFrame:
    """Formato largo (tabla, anio, territorio_id, columna, valor) de una tabla del INE (.xls o .xlsx)."""
    import xlrd  # solo para este control (decisión del mantenedor, #189)

    libro = xlrd.open_workbook(file_contents=xls, formatting_info=True)
    hoja = libro.sheet_by_index(0)
    celdas = {(r, c): hoja.cell_value(r, c) for r in range(hoja.nrows) for c in range(hoja.ncols)
              if hoja.cell_value(r, c) not in ("", None)}
    combinadas = [(r1 + 1, c1 + 1, r2, c2) for r1, r2, c1, c2 in hoja.merged_cells]  # a la convención de mec_anuario
    filas_anio = sorted(r for (r, c), v in celdas.items() if c == 0 and re.fullmatch(r"\s*(19|20)\d\d(\.0)?\s*", str(v)))
    if not filas_anio:
        raise ValueError(f"{tabla}: no encuentro las filas de año")
    # encabezado: entre el título y el primer año; celdas combinadas propagadas a la derecha
    inicio = next(r for r in range(filas_anio[0]) if any(isinstance(celdas.get((r, c)), str) and c > 0 for c in range(hoja.ncols)))
    hdr = {}
    for f1, c1, f2, c2 in combinadas:
        v = celdas.get((f1 - 1, c1 - 1))
        for r in range(f1 - 1, f2):
            for c in range(c1 - 1, c2):
                if inicio <= r < filas_anio[0] and v is not None:
                    hdr[(r, c)] = v
    for (r, c), v in celdas.items():
        if inicio <= r < filas_anio[0]:
            hdr.setdefault((r, c), v)
    columnas = {}
    for c in range(1, hoja.ncols):
        partes = [" ".join(str(hdr[(r, c)]).split()) for r in range(inicio, filas_anio[0]) if (r, c) in hdr]
        if partes:
            columnas[c] = "/".join(partes)
    salida = []
    for i, fa in enumerate(filas_anio):
        anio = str(int(float(celdas[(fa, 0)])))
        fin = filas_anio[i + 1] if i + 1 < len(filas_anio) else hoja.nrows
        for r in range(fa + 1, fin):
            rot = celdas.get((r, 0))
            terr = _territorio(str(rot)) if isinstance(rot, str) else None
            if terr is None:
                continue
            for c, col in columnas.items():
                v = celdas.get((r, c))
                if isinstance(v, (int, float)):
                    salida.append({"tabla": tabla, "anio": anio, "territorio_id": terr, "columna": col, "valor": float(v)})
    return pd.DataFrame(salida)


def comparar(ine: pd.DataFrame, obs: pd.DataFrame, porcentajes: set[str]) -> dict:
    """AC-E23: diferencias entre cada columna del INE y el indicador del MEC que es la misma medida."""
    o = obs[obs.periodo.isin(set(ine.anio))].assign(valor=lambda d: d.valor.astype(float))
    pais = o[o.territorio_id == mec.PAIS]
    por_valor = {}
    for (ind, per), v in pais.set_index(["indicador", "periodo"]).valor.items():
        por_valor.setdefault((per, round(v, 1) if ind in porcentajes else v), set()).add(ind)
    val = o.set_index(["indicador", "territorio_id", "periodo"]).valor
    pares, sin_par, diferencias, comparados = [], [], [], 0
    for (tabla, col), g in ine.groupby(["tabla", "columna"]):
        gp = g[g.territorio_id == mec.PAIS]
        if gp.empty:
            continue
        cand = None
        for r in gp.itertuples():
            claves = por_valor.get((r.anio, r.valor), set()) | por_valor.get((r.anio, round(r.valor, 1)), set())
            cand = claves if cand is None else cand & claves
        if not cand:
            sin_par.append(f"{tabla} «{col}»")
            continue
        ind = sorted(cand, key=lambda i: (i.count("__"), i))[0]  # el más simple si hay varios iguales
        pares.append(f"{tabla} «{col}» = `{ind}`")
        for r in g.itertuples():
            k = (ind, r.territorio_id, r.anio)
            if k not in val.index:
                continue
            mio = val[k]
            comparados += 1
            igual = round(mio, 1) == round(r.valor, 1) if ind in porcentajes else mio == r.valor
            if not igual:
                diferencias.append(f"{tabla} «{col}» {r.anio} {r.territorio_id.split('/', 1)[1]}: INE {r.valor:g}, MEC `{ind}` {mio:g}")
    return {"pares": pares, "sin_par": sin_par, "diferencias": diferencias, "comparados": comparados}


def leer_capturadas(crudo: Path) -> tuple[pd.DataFrame | None, dict]:
    """Las tablas del INE guardadas por `capturar`, si están (si no, el control no corre), y el manifiesto con las
    tablas que no se pueden comparar por territorio (series nacionales, o por categoría con años en columnas)."""
    d = Path(crudo) / CARPETA
    if not (d / "control_ine.json").exists():
        return None, {}
    manifiesto = json.loads((d / "control_ine.json").read_text(encoding="utf-8"))
    manifiesto["no_comparables"] = []
    partes = []
    for t, info in sorted(manifiesto["tablas"].items(), key=lambda kv: int(kv[0].split(".")[-1])):
        datos = (d / info["archivo"]).read_bytes()
        if hashlib.sha256(datos).hexdigest() != info["sha256"]:
            raise ValueError(f"{d / info['archivo']} no coincide con su sha256")
        try:
            tabla = leer_tabla(datos, t)
        except ValueError:
            tabla = pd.DataFrame()
        if tabla.empty or tabla.territorio_id.nunique() < 3:
            manifiesto["no_comparables"].append(t)
        else:
            partes.append(tabla)
    return (pd.concat(partes, ignore_index=True) if partes else None), manifiesto


def lineas_reporte(r: dict | None, manifiesto: dict) -> list[str]:
    """AC-E23 (advertencia): la sección del control con el INE."""
    lineas = ["### Control con el Anuario Estadístico Nacional del INE (AC-E23, advertencia)", ""]
    if r is None:
        return lineas + ["No hay tablas del INE guardadas (`pipeline/mec_anuario_captura.py --control-ine`): el control no corrió."]
    lineas += [f"Tablas del INE del {manifiesto.get('fecha', '—')} ({manifiesto.get('pagina', '')}). Los valores del INE "
               "nunca se cargan.",
               f"Columnas del INE con la misma medida en el MEC: {len(r['pares'])}; valores comparados por territorio y "
               f"año: {r['comparados']}; diferencias: {len(r['diferencias'])}.",
               *[f"- {d}" for d in r["diferencias"]]]
    if r["sin_par"]:
        lineas.append(f"Sin medida igual en el MEC: {'; '.join(r['sin_par'])}.")
    if manifiesto.get("no_comparables"):
        lineas.append(f"No comparables por territorio: {', '.join(manifiesto['no_comparables'])}.")
    if manifiesto.get("errores"):
        lineas.append("Errores de descarga: " + "; ".join(f"{e['tabla']}: {e['error']}" for e in manifiesto["errores"]) + ".")
    return lineas
