"""F4.5a (#188): controles de calidad de los datos de educación (MEC) y su parte del reporte (AC-E17…E22).

Sobre las observaciones cargadas por `mec_anuario_cargar.py`, antes de publicar. Una falla frena la carga, salvo:

- AC-E18: si «RESTO DEL PAÍS» no es TOTAL − MONTEVIDEO en un indicador y año, esa fila del Interior se saltea y se
  reporta (lo mismo si el territorio `region/interior` no existe); los demás controles ya no la miran;
- AC-E22: los cambios de más de ±20 % entre años son solo advertencia;
- las excepciones de la fuente de `fuentes/mec_anuario/mapeo_manual.yml` (`controles_excepciones`), cada una
  acotada a sus indicadores (y territorios, si los dice) y con un motivo: lo publicado no cierra y se guarda tal
  cual; queda como advertencia. Una falla en otro indicador o territorio del mismo cuadro y año frena igual.

AC-E17  departamentos: Montevideo + los 18 = TOTAL en cada conteo de un cuadro tipo A.
AC-E19  desgloses: en cada grupo del encabezado, varón + mujer (+ sin dato), pública + privada y urbana + rural
        suman su total; en los B y C, las categorías suman el total (`particiones` para filas jerárquicas). Las
        partes que el encabezado no dice se declaran en `desgloses_extra`.
AC-E20  conteos ≥ 0, tasas entre 0 y 100, nada por debajo de departamento, B y C solo en territorios que el
        cuadro nombra (país, o Montevideo y el Interior bajo «TOTAL MONTEVIDEO» / «TOTAL RESTO DEL PAÍS»).
AC-E21  cada indicador de un cuadro tipo A tiene sus 21 territorios (país, Interior y los 19 departamentos) en cada
        año; un territorio falta sin falla solo si el anuario lo publicó sin dato («s/d», «-») o si es la fila del
        Interior salteada por AC-E18 (o está en `huecos`). Solo en los años parseados en esta corrida.
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
PATRONES = ({"v", "m"}, {"publica", "privada"}, {"urbana", "rural"}, {"urbano", "rural"})
AGRUPADORES = {"sexo", "forma de administracion", "area demografica", "area", "tipo de educacion", "categoria"}
SEXO = {"varon": "v", "varones": "v", "v": "v", "mujer": "m", "mujeres": "m", "m": "m"}


def _norm(ruta: str) -> tuple[str, ...]:
    """La misma normalización que D6 en scripts/inventario_mec.py: sin tildes, «SEXO» fuera, varón → v, mujer → m."""
    segs = [re.sub(r"\*+|\s*\d$|\.$", "", plegar(x)).strip() for x in ruta.split("/")]
    return tuple(SEXO.get(x, x) for x in segs if x not in ("sexo", "por sexo"))


def _corto(t: str) -> str:
    return t.split("/", 1)[1] if "/" in t else t


class Excepciones:
    """`controles_excepciones` del archivo manual: control → cuadro → año → {motivo, indicadores, territorios?}."""

    def __init__(self, manual: dict):
        self.datos = manual.get("controles_excepciones") or {}

    def motivo(self, control: str, cod: str, anio, indicador: str, territorio: str | None = None) -> str | None:
        e = ((self.datos.get(control) or {}).get(cod) or {}).get(int(anio))
        if not e or indicador not in e.get("indicadores", []):
            return None
        if territorio is not None and e.get("territorios") and _corto(territorio) not in e["territorios"]:
            return None
        return e["motivo"]


class Resultado:
    def __init__(self):
        self.controles = Controles()
        self.advertencias: list[str] = []
        self.region_salteada: set[tuple[str, str]] = set()  # (indicador, período) sin fila del Interior (AC-E18)
        self.saltos = pd.DataFrame()

    def chk(self, nombre: str, fallas: list[str], excepciones: list[str], extra: str = ""):
        detalle = (f"{len(fallas)} casos: " + "; ".join(fallas[:3])) if fallas else \
            "; ".join(x for x in (f"{len(excepciones)} de la fuente, listados" if excepciones else "", extra) if x)
        self.controles.chk(nombre, not fallas, detalle)
        self.advertencias += excepciones


def _desgloses(por: dict[tuple, str], extras: list[dict]) -> list[tuple[tuple, list[tuple]]]:
    """(ruta del total, [rutas de las partes]) de un cuadro y año, a partir del árbol de rutas del encabezado."""
    rutas = set(por)

    def columna(x):
        return x if x in rutas else (x + ("total",) if x + ("total",) in rutas else None)

    prefijos = {r[:i] for r in rutas for i in range(len(r))}
    salida = []
    for p in prefijos:
        hijos = {r[len(p)] for r in rutas if len(r) > len(p) and r[:len(p)] == p}
        for patron in PATRONES:
            if not patron <= hijos:
                continue
            partes = [columna(p + (s,)) for s in sorted(patron) + (["sin dato"] if "sin dato" in hijos else [])]
            if None in partes:
                continue
            candidatos = [p, p + ("total",)]
            if p and p[-1] in AGRUPADORES | {"total"}:
                candidatos += [p[:-1], p[:-1] + ("total",)]
            if p and set(p) <= AGRUPADORES | {"total"}:
                candidatos.append(("total",))
            total = next((c for c in candidatos if c in rutas and c not in partes), None)
            if total:
                salida.append((total, partes))
    for x in extras:
        total, partes = _norm(x["total"]), [_norm(y) for y in x["partes"]]
        if total in rutas and all(y in rutas for y in partes):
            salida = [(t, p) for t, p in salida if t != total]  # la declaración manda sobre lo inferido
            salida.append((total, partes))
    return salida


def controles(obs: pd.DataFrame, fuente: dict, manual: dict, derivados: set[str], sin_dato: set | None = None,
              anios_parseados: set[str] | None = None, hay_interior: bool = True) -> Resultado:
    res, exc = Resultado(), Excepciones(manual)
    sin_dato = sin_dato or set()
    cuadro_de, ruta_de, tipo_de = {}, {}, {}
    for cod, e in fuente["cuadros"].items():
        for anio, m in (e.get("mapeo") or {}).items():
            for x in m or []:
                if not x.get("omitir"):
                    per = str(x.get("anio", anio))
                    cuadro_de[x["id"]] = cod
                    ruta_de[(x["id"], per)] = _norm(x.get("concepto", x["ruta"]))
                    tipo_de[(cod, per)] = e["tipos"].get(anio)
    base = obs.indicador.str.split("__").str[0]
    obs = obs.assign(cuadro=base.map(cuadro_de), nivel=obs.territorio_id.str.split("/").str[1],
                     valor=obs.valor.astype(float))  # la carga guarda enteros de Python (dtype object)
    conteos = obs[~obs.indicador.isin(derivados) & obs.cuadro.notna()]

    # AC-E20
    fuera = obs[~obs.nivel.isin(NIVELES)]
    negativos = conteos[conteos.valor < 0]
    tasas = obs[obs.indicador.isin(derivados)]
    malas = tasas[(tasas.valor < 0) | (tasas.valor > 100)]
    # B y C: por el tipo del cuadro en ese año (#172: II-5.1.1 es A y carga la DGETP por departamento como categoría)
    es_bc = [tipo_de.get((c, p)) in ("B", "C") for c, p in zip(obs.cuadro, obs.periodo)]
    bc = obs[obs.indicador.str.contains("__") & pd.Series(es_bc, index=obs.index)
             & ~obs.territorio_id.isin({PAIS, MVD, INTERIOR})]
    fallas = [f"{len(d)} {t}" for d, t in ((fuera, "por debajo de departamento"), (negativos, "conteos negativos"),
                                           (malas, "tasas fuera de 0–100"), (bc, "filas B/C en otro territorio")) if len(d)]
    res.chk("AC-E20 Niveles, conteos ≥ 0, tasas entre 0 y 100, B y C en territorios nombrados", fallas, [])

    a = conteos[~conteos.indicador.str.contains("__") & conteos.territorio_id.isin(TERRITORIOS_A)]
    w = a.pivot_table(index=["indicador", "periodo"], columns="territorio_id", values="valor", aggfunc="first")
    for t in TERRITORIOS_A:
        if t not in w:
            w[t] = float("nan")

    # AC-E18 primero: lo que saltea ya no lo miran los demás controles
    if not hay_interior:
        for ind, per in w[w[INTERIOR].notna()].index:
            res.region_salteada.add((ind, per))
        res.advertencias.append(f"AC-E18 el territorio {INTERIOR} no existe: se saltean las {len(res.region_salteada)} "
                                "filas de «RESTO DEL PAÍS»")
    else:
        tres = w[w[[PAIS, MVD, INTERIOR]].notna().all(axis=1)]
        for (ind, per), f in tres[tres[PAIS] - tres[MVD] != tres[INTERIOR]].iterrows():
            res.region_salteada.add((ind, per))
            res.advertencias.append(f"AC-E18 {cuadro_de[ind]} {per} `{ind}`: Resto del país {f[INTERIOR]:g} ≠ "
                                    f"{f[PAIS]:g} − {f[MVD]:g}; no se carga la fila del Interior")
        # #241 (revisión): en los cuadros A con categorías del territorio (PÚBLICO/PRIVADO bajo RESTO DEL PAÍS, II-7.1.x)
        # la categoría del Interior también tiene que ser TOTAL − MONTEVIDEO de la misma categoría (§4)
        con_cat = {c for c, e in fuente["cuadros"].items() if (e.get("filas_de_establecimiento") or {}).get("categorias")}
        ca = conteos[conteos.indicador.str.contains("__") & conteos.territorio_id.isin({PAIS, MVD, INTERIOR})]
        ca = ca[ca.indicador.str.split("__").str[0].map(cuadro_de).isin(con_cat)]
        if len(ca):
            wc = ca.pivot_table(index=["indicador", "periodo"], columns="territorio_id", values="valor", aggfunc="first")
            if {PAIS, MVD, INTERIOR} <= set(wc.columns):
                tres_c = wc[wc[[PAIS, MVD, INTERIOR]].notna().all(axis=1)]
                for (ind, per), f in tres_c[tres_c[PAIS] - tres_c[MVD] != tres_c[INTERIOR]].iterrows():
                    res.region_salteada.add((ind, per))
                    res.advertencias.append(f"AC-E18 {cuadro_de[ind.split('__')[0]]} {per} `{ind}`: Resto del país "
                                            f"{f[INTERIOR]:g} ≠ {f[PAIS]:g} − {f[MVD]:g}; no se carga la fila del Interior")
    sin_probar18 = int((w[[PAIS, MVD]].notna().all(axis=1) & w[INTERIOR].isna()).sum())
    res.controles.chk("AC-E18 Resto del país = TOTAL − MONTEVIDEO", True,
                      "; ".join(x for x in (f"{len(res.region_salteada)} filas del Interior salteadas" if res.region_salteada else "",
                                            f"{sin_probar18} sin fila del Interior para probar" if sin_probar18 else "") if x))

    # AC-E17
    fallas, excs = [], []
    completos = w[w[PAIS].notna() & w[DEPTOS].notna().all(axis=1)]
    for (ind, per), f in completos[completos[DEPTOS].sum(axis=1) != completos[PAIS]].iterrows():
        cod = cuadro_de[ind]
        texto = f"{cod} {per} `{ind}`: país {f[PAIS]:g}, suma de los departamentos {f[DEPTOS].sum():g}"
        if (m := exc.motivo("AC-E17", cod, per, ind)):
            excs.append(f"{texto} ({m})")
        else:
            fallas.append(texto)
    incompletos = int((w[PAIS].notna() & ~w[DEPTOS].notna().all(axis=1)).sum())
    res.chk("AC-E17 Montevideo + 18 departamentos = TOTAL", fallas, excs,
            f"{incompletos} indicador-año sin probar (algún departamento sin valor)" if incompletos else "")

    # AC-E19
    val = conteos.set_index(["indicador", "territorio_id", "periodo"]).valor
    salteada = {(i, INTERIOR, p) for i, p in res.region_salteada}
    fallas, excs, probados = [], [], 0
    por_cuadro = collections.defaultdict(dict)
    for (ind, per), r in ruta_de.items():
        por_cuadro[(cuadro_de[ind], per)][r] = ind
    extras = manual.get("desgloses_extra") or {}
    territorios = sorted(set(conteos.territorio_id))
    # #233: en los cuadros B y C cada valor lleva su categoría (`__categoria`); el desglose de columnas se prueba en
    # cada fila (categoría) del cuadro, no solo con el id base (antes no se probaba nunca en esos cuadros).
    cats = collections.defaultdict(set)
    for i in conteos.indicador[conteos.indicador.str.contains("__", regex=False)].unique():
        b, c = i.split("__", 1)
        cats[b].add("__" + c)
    for (cod, per), por in por_cuadro.items():
        sufijos = [""] + sorted({c for i in por.values() for c in cats.get(i, ())})
        for total, partes in _desgloses(por, extras.get(cod) or []):
            for suf in sufijos:
                for terr in territorios:
                    kt, ks = (por[total] + suf, terr, per), [(por[x] + suf, terr, per) for x in partes]
                    if (kt in salteada or any(k in salteada for k in ks) or kt not in val.index
                            or not all(k in val.index for k in ks)):
                        continue
                    probados += 1
                    suma = sum(val[k] for k in ks)
                    if val[kt] == suma:
                        continue
                    fila = f" [{suf[2:]}]" if suf else ""
                    texto = (f"{cod} {per} {_corto(terr)}{fila}: «{'/'.join(total)}» {val[kt]:g} ≠ "
                             + " + ".join("/".join(x) for x in partes) + f" = {suma:g}")
                    if (m := exc.motivo("AC-E19", cod, per, por[total] + suf, terr)):
                        excs.append(f"{texto} ({m})")
                    else:
                        fallas.append(texto)
    particiones = manual.get("particiones") or {}
    cat = conteos[conteos.indicador.str.contains("__")].assign(
        base=lambda d: d.indicador.str.split("__").str[0], categoria=lambda d: d.indicador.str.split("__", n=1).str[1])
    no_aditivos = manual.get("no_aditivos") or {}
    for (b, terr, per), g in cat.groupby(["base", "territorio_id", "periodo"]):
        v = dict(zip(g.categoria, g.valor))
        if "total" not in v or len(v) == 1:  # #233: sin categorías cargadas (p. ej. horas 2020–21) no hay qué sumar
            continue
        cod = cuadro_de[b]
        if (na := no_aditivos.get(cod)) and na["patron"] in b:
            continue  # #225: un promedio publicado no se suma entre categorías
        for tot, partes in particiones.get(cod) or [["total", [k for k in v if k != "total"]]]:
            if tot in v and all(p in v for p in partes):
                probados += 1
                if v[tot] != sum(v[p] for p in partes):
                    texto = f"{cod} {per} `{b}` {_corto(terr)}: {tot} {v[tot]:g} ≠ {' + '.join(partes)} = {sum(v[p] for p in partes):g}"
                    if (m := exc.motivo("AC-E19", cod, per, b, terr)):
                        excs.append(f"{texto} ({m})")
                    else:
                        fallas.append(texto)
    res.chk(f"AC-E19 Desgloses que suman su total ({probados} probados)", fallas, excs)

    # AC-E21 (por indicador y año, en los años parseados)
    fallas, excs = [], []
    huecos = manual.get("huecos") or {}
    publicados = set(sin_dato)
    for (ind, per), f in w.iterrows():
        if "__" in ind:
            continue  # #172: una categoría de un cuadro A (II-5.1.1: la DGETP por departamento) no tiene sus 21 territorios
        cod = cuadro_de[ind]
        if tipo_de.get((cod, per)) != "A" or (anios_parseados is not None and per not in anios_parseados):
            continue
        faltan = [t for t in sorted(TERRITORIOS_A) if pd.isna(f[t]) and (ind, t, per) not in publicados
                  and not (t == INTERIOR and (ind, per) in res.region_salteada)]
        if faltan:
            texto = f"{cod} {per} `{ind}`: sin valor ni «sin dato» publicado en {[_corto(t) for t in faltan][:4]}"
            h = (huecos.get(cod) or {}).get(int(per)) or {}
            if h and set(map(_corto, faltan)) <= set(h.get("territorios", [])):
                excs.append(f"{texto} ({h['motivo']})")
            else:
                fallas.append(texto)
    con_algo = set(w.index) | {(i, p) for i, _, p in publicados}
    for (ind, per) in ruta_de:
        cod = cuadro_de[ind]
        if (tipo_de.get((cod, per)) == "A" and (anios_parseados is None or per in anios_parseados)
                and (ind, per) not in con_algo):
            fallas.append(f"{cod} {per} `{ind}`: mapeado y sin ningún valor ni «sin dato»")
    res.chk("AC-E21 Cada indicador de un cuadro A con sus 21 territorios", fallas, excs,
            "" if anios_parseados is None else f"años probados: {', '.join(sorted(anios_parseados)) or 'ninguno'}")

    # AC-E22 (advertencia; sin las filas del Interior salteadas)
    serie = conteos[~conteos.indicador.str.startswith("edu_serie")].copy()
    if res.region_salteada:
        claves = list(zip(serie.indicador, serie.periodo))
        serie = serie[[not (t == INTERIOR and k in res.region_salteada) for t, k in zip(serie.territorio_id, claves)]]
    serie["anio"] = serie.periodo.astype(int)
    s = serie.sort_values("anio").groupby(["indicador", "territorio_id"])
    serie["antes"], serie["anio_antes"] = s.valor.shift(), s.anio.shift()
    res.saltos = serie[(serie.anio_antes == serie.anio - 1) & (serie.antes > 0)
                       & ((serie.valor - serie.antes).abs() / serie.antes > CAMBIO)]
    return res


def lineas_saltos(saltos: pd.DataFrame, n: int = 15) -> list[str]:
    """AC-E22: los cambios de más de ±20 % entre años consecutivos (advertencia), los más grandes primero."""
    if saltos.empty:
        return ["Cambios de más de ±20 % entre años consecutivos (AC-E22, advertencia): ninguno."]
    s = saltos.assign(rel=(saltos.valor - saltos.antes) / saltos.antes).sort_values("rel", key=abs, ascending=False)
    lineas = [f"Cambios de más de ±20 % entre años consecutivos (AC-E22, advertencia): {len(s)} "
              f"(en {s.indicador.nunique()} indicadores). Los {min(n, len(s))} más grandes:"]
    lineas += [f"- `{r.indicador}`, {_corto(r.territorio_id)}, {int(r.anio_antes)} → {int(r.anio)}: "
               f"{r.antes:g} → {r.valor:g} ({r.rel:+.0%})" for r in s.head(n).itertuples()]
    return lineas
