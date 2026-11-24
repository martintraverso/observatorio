"""F4.5a (#188): controles de calidad de los datos de educación (MEC) y su parte del reporte (AC-E17…E22).

Sobre las observaciones cargadas por `mec_anuario_cargar.py`, antes de publicar. Una falla frena la carga, salvo:

- AC-E18: si «RESTO DEL PAÍS» no es TOTAL − MONTEVIDEO, esas filas de región se saltean y se reportan;
- AC-E22: los cambios de más de ±20 % entre años son solo advertencia;
- las excepciones de la fuente listadas con su motivo en `fuentes/mec_anuario/mapeo_manual.yml`
  (`controles_excepciones`): el cuadro-año publicado no cierra y se guarda tal cual; queda como advertencia.

AC-E17  departamentos: Montevideo + los 18 = TOTAL en cada conteo de un cuadro tipo A.
AC-E19  desgloses: varón + mujer (+ sin dato) = su total; pública + privada = total; urbana + rural = total;
        en los cuadros B y C, las categorías = el total (con las particiones declaradas para filas jerárquicas).
AC-E20  conteos ≥ 0, tasas entre 0 y 100, nada por debajo de departamento, B y C solo en territorios que el
        cuadro nombra (país, o Montevideo y el Interior bajo «TOTAL MONTEVIDEO» / «TOTAL RESTO DEL PAÍS»).
AC-E21  cada cuadro tipo A tiene datos para sus 21 territorios (país, Interior y los 19 departamentos) en cada año,
        salvo los huecos listados (`huecos`).
"""

from __future__ import annotations

import collections
import re

import pandas as pd
from mec_anuario import plegar

from comun.controles import Controles

PAIS, MVD, INTERIOR = "INE-2023/pais/UY", "INE-2023/departamento/01", "INE-2023/region/interior"
DEPTOS = [f"INE-2023/departamento/{i:02d}" for i in range(1, 20)]
TERRITORIOS_A = {PAIS, INTERIOR, *DEPTOS}
NIVELES = {"pais", "region", "departamento"}
CAMBIO = 0.20
PARES = ((("v",), ("m",)), (("publica",), ("privada",)), (("urbana",), ("rural",)), (("urbano",), ("rural",)))


def _norm(ruta: str) -> tuple[str, ...]:
    """La misma normalización que D6 en scripts/inventario_mec.py: sin tildes, «SEXO» fuera, varón → v, mujer → m."""
    sexo = {"varon": "v", "varones": "v", "v": "v", "mujer": "m", "mujeres": "m", "m": "m"}
    segs = [re.sub(r"\*+|\s*\d$|\.$", "", plegar(x)).strip() for x in ruta.split("/")]
    return tuple(sexo.get(x, x) for x in segs if x not in ("sexo", "por sexo"))


def _excepcion(manual: dict, control: str, cod: str, anio) -> str | None:
    return ((manual.get("controles_excepciones") or {}).get(control) or {}).get(cod, {}).get(int(anio))


class Resultado:
    def __init__(self):
        self.controles = Controles()
        self.advertencias: list[str] = []
        self.region_salteada: set[tuple[str, str]] = set()  # (indicador, período) sin fila de región (AC-E18)

    def chk(self, nombre, fallas: list[str], excepciones: list[str]):
        self.controles.chk(nombre, not fallas, f"{len(fallas)} casos: " + "; ".join(fallas[:3]) if fallas else
                           (f"OK; {len(excepciones)} de la fuente listados" if excepciones else ""))
        self.advertencias += excepciones


def controles(obs: pd.DataFrame, fuente: dict, manual: dict, derivados: set[str]) -> Resultado:
    res = Resultado()
    cuadro_de, ruta_de, tipo_de = {}, {}, {}
    for cod, e in fuente["cuadros"].items():
        for anio, m in (e.get("mapeo") or {}).items():
            for x in m or []:
                if not x.get("omitir"):
                    cuadro_de[x["id"]] = cod
                    ruta_de[(x["id"], str(x.get("anio", anio)))] = _norm(x.get("concepto", x["ruta"]))
                    tipo_de[(cod, str(x.get("anio", anio)))] = e["tipos"].get(anio)
    base = obs.indicador.str.split("__").str[0]
    obs = obs.assign(cuadro=base.map(cuadro_de), nivel=obs.territorio_id.str.split("/").str[1],
                     valor=obs.valor.astype(float))  # la carga guarda enteros de Python (dtype object)
    conteos = obs[~obs.indicador.isin(derivados) & obs.cuadro.notna()]

    # AC-E20
    fuera = obs[~obs.nivel.isin(NIVELES)]
    negativos = conteos[conteos.valor < 0]
    tasas = obs[obs.indicador.isin(derivados)]
    malas = tasas[(tasas.valor < 0) | (tasas.valor > 100)]
    bc = obs[obs.indicador.str.contains("__") & ~obs.territorio_id.isin({PAIS, MVD, INTERIOR})]
    res.chk("AC-E20 Niveles, conteos ≥ 0, tasas entre 0 y 100, B y C en territorios nombrados",
            [f"{len(fuera)} por debajo de departamento"] * bool(len(fuera)) + [f"{len(negativos)} conteos negativos"] * bool(len(negativos))
            + [f"{len(malas)} tasas fuera de 0–100"] * bool(len(malas)) + [f"{len(bc)} filas B/C en otro territorio"] * bool(len(bc)), [])

    a = conteos[~conteos.indicador.str.contains("__") & conteos.territorio_id.isin(TERRITORIOS_A)]
    w = a.pivot_table(index=["indicador", "periodo"], columns="territorio_id", values="valor", aggfunc="first")
    for t in TERRITORIOS_A:
        if t not in w:
            w[t] = float("nan")

    # AC-E17
    fallas, exc = [], []
    completos = w[w[PAIS].notna() & w[DEPTOS].notna().all(axis=1)]
    for (ind, per), f in completos[completos[DEPTOS].sum(axis=1) != completos[PAIS]].iterrows():
        cod = cuadro_de[ind]
        texto = f"{cod} {per} `{ind}`: país {f[PAIS]:g}, suma {f[DEPTOS].sum():g}"
        if (m := _excepcion(manual, "AC-E17", cod, per)):
            exc.append(f"{texto} ({m})")
        else:
            fallas.append(texto)
    res.chk("AC-E17 Montevideo + 18 departamentos = TOTAL", fallas, exc)

    # AC-E18 (no frena: saltea la región)
    tres = w[w[[PAIS, MVD, INTERIOR]].notna().all(axis=1)]
    for (ind, per), f in tres[tres[PAIS] - tres[MVD] != tres[INTERIOR]].iterrows():
        res.region_salteada.add((ind, per))
        res.advertencias.append(f"AC-E18 {cuadro_de[ind]} {per} `{ind}`: Resto del país {f[INTERIOR]:g} ≠ "
                                f"{f[PAIS]:g} − {f[MVD]:g}; no se carga la fila del Interior")
    res.controles.chk("AC-E18 Resto del país = TOTAL − MONTEVIDEO", True,
                      f"{len(res.region_salteada)} filas del Interior salteadas" if res.region_salteada else "")

    # AC-E19
    val = conteos.set_index(["indicador", "territorio_id", "periodo"]).valor
    fallas, exc, probados = [], [], 0
    por_cuadro = collections.defaultdict(dict)
    for (ind, per), r in ruta_de.items():
        por_cuadro[(cuadro_de[ind], per)][r] = ind
    for (cod, per), por in por_cuadro.items():
        for t in list(por):
            pre = t[:-1]
            for p1, p2 in PARES:
                if t[-1:] != p1 or pre + p2 not in por:
                    continue
                hijos = [pre + p1, pre + p2] + ([pre + ("sin dato",)] if pre + ("sin dato",) in por else [])
                total = next((x for x in (pre + ("total",), pre) if x in por and x not in hijos), None)
                if total is None:
                    continue
                for terr in TERRITORIOS_A:
                    ks = [(por[h], terr, per) for h in hijos]
                    kt = (por[total], terr, per)
                    if kt in val.index and all(k in val.index for k in ks):
                        probados += 1
                        if val[kt] != sum(val[k] for k in ks):
                            texto = f"{cod} {per} {terr.split('/', 1)[1]} «{'/'.join(total)}»: {val[kt]:g} ≠ {sum(val[k] for k in ks):g}"
                            if (m := _excepcion(manual, "AC-E19", cod, per)):
                                exc.append(f"{texto} ({m})")
                            else:
                                fallas.append(texto)
    # categorías de los cuadros B y C
    particiones = manual.get("particiones") or {}
    cat = conteos[conteos.indicador.str.contains("__")].assign(
        base=lambda d: d.indicador.str.split("__").str[0], categoria=lambda d: d.indicador.str.split("__").str[-1])
    for (b, terr, per), g in cat.groupby(["base", "territorio_id", "periodo"]):
        v = dict(zip(g.categoria, g.valor))
        if "total" not in v:
            continue
        cod = cuadro_de[b]
        reglas = particiones.get(cod) or [["total", [k for k in v if k != "total"]]]
        for tot, partes in reglas:
            if tot in v and all(p in v for p in partes):
                probados += 1
                if v[tot] != sum(v[p] for p in partes):
                    texto = f"{cod} {per} `{b}` {terr.split('/', 1)[1]}: {tot} {v[tot]:g} ≠ {sum(v[p] for p in partes):g}"
                    if (m := _excepcion(manual, "AC-E19", cod, per)):
                        exc.append(f"{texto} ({m})")
                    else:
                        fallas.append(texto)
    res.chk(f"AC-E19 Desgloses que suman su total ({probados} probados)", fallas, exc)

    # AC-E21
    fallas, exc = [], []
    huecos = manual.get("huecos") or {}
    con_datos = a.groupby(["cuadro", "periodo"]).territorio_id.agg(set)
    for (cod, per), terrs in con_datos.items():
        if tipo_de.get((cod, per)) != "A":
            continue
        faltan = sorted(TERRITORIOS_A - terrs)
        if faltan:
            texto = f"{cod} {per}: sin datos en {[f.split('/', 1)[1] for f in faltan][:4]}"
            if (m := (huecos.get(cod) or {}).get(int(per))):
                exc.append(f"{texto} ({m})")
            else:
                fallas.append(texto)
    res.chk("AC-E21 Cada cuadro tipo A con sus 21 territorios", fallas, exc)

    # AC-E22 (advertencia)
    serie = conteos[~conteos.indicador.str.startswith("edu_serie")].copy()
    serie["anio"] = serie.periodo.astype(int)
    s = serie.sort_values("anio").groupby(["indicador", "territorio_id"])
    serie["antes"], serie["anio_antes"] = s.valor.shift(), s.anio.shift()
    saltos = serie[(serie.anio_antes == serie.anio - 1) & (serie.antes > 0)
                   & ((serie.valor - serie.antes).abs() / serie.antes > CAMBIO)]
    res.saltos = saltos
    return res


def lineas_saltos(saltos: pd.DataFrame, n: int = 15) -> list[str]:
    """AC-E22: los cambios de más de ±20 % entre años consecutivos (advertencia), los más grandes primero."""
    if saltos.empty:
        return ["Cambios de más de ±20 % entre años consecutivos (AC-E22, advertencia): ninguno."]
    s = saltos.assign(rel=(saltos.valor - saltos.antes) / saltos.antes).sort_values("rel", key=abs, ascending=False)
    lineas = [f"Cambios de más de ±20 % entre años consecutivos (AC-E22, advertencia): {len(s)} "
              f"(en {s.indicador.nunique()} indicadores). Los {min(n, len(s))} más grandes:"]
    lineas += [f"- `{r.indicador}`, {r.territorio_id.split('/', 1)[1]}, {int(r.anio_antes)} → {int(r.anio)}: "
               f"{r.antes:g} → {r.valor:g} ({r.rel:+.0%})" for r in s.head(n).itertuples()]
    return lineas
