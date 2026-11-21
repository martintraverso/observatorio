"""F3.5 (#129): controles de calidad de las series de ingresos (ECH) y su parte del reporte de validación.

Sobre las observaciones vigentes de la fuente (formato largo: indicador, territorio_id, periodo, tipo_periodo,
valor). Una falla frena la carga; AC-I15 es solo advertencia.

- AC-I12  todos los valores > 0.
- AC-I13  mismo territorio, período y variante: per cápita < hogar; con aguinaldo ≥ sin; con valor locativo ≥ sin.
- AC-I14  mismo indicador y período: el Interior está entre sus dos partes; el país, entre Montevideo y el Interior.
- AC-I15  (advertencia) el total del año está a ±5 % del promedio de sus cuatro trimestres.
- AC-I16  cada año completo (2016 al último con los cuatro trimestres) tiene 4 trimestres y el total; el año en
          curso, solo sus trimestres publicados, desde el primero y sin total.
- AC-I17  ningún valor en departamentos distintos de Montevideo ni en niveles menores que departamento.
"""

from __future__ import annotations

import pandas as pd

from comun.controles import Controles

PAIS, MVD = "INE-2023/pais/UY", "INE-2023/departamento/01"
INTERIOR, I5000, MENORES = (f"INE-2023/region/{c}" for c in ("interior", "interior-5000", "interior-menores"))
NIVELES = {"pais", "region", "departamento"}
VARIANTES = ["cagu_cvl", "sagu_cvl", "cagu_svl", "sagu_svl"]
PRIMER_ANIO = 2016
TOLERANCIA_TOTAL = 0.05
TOLERANCIA = 1e-9  # comparación de valores publicados (los iguales no son una falla)


def _ejemplos(df: pd.DataFrame, n: int = 3) -> str:
    return "; ".join(" ".join(str(v) for v in fila) for fila in df.head(n).itertuples(index=False))


def _orden(c: Controles, w: pd.DataFrame, nombre: str, pares: list[tuple[str, str, bool]]) -> None:
    """Para cada (mayor, menor, estricto) de columnas presentes, `mayor > menor` (o ≥)."""
    malos = []
    for mayor, menor, estricto in pares:
        if mayor not in w or menor not in w:
            continue
        x = w[[mayor, menor]].dropna()
        mal = x[x[mayor] <= x[menor] + (TOLERANCIA if estricto else -TOLERANCIA)]
        malos += [(i, mayor, menor) for i in mal.index]
    c.chk(nombre, not malos, f"{len(malos)} casos: " + "; ".join(map(str, malos[:3])) if malos else "")


def controles(obs: pd.DataFrame) -> tuple[Controles, list[str]]:
    c, advertencias = Controles(), []
    nivel = obs.territorio_id.str.split("/").str[1]

    # AC-I17 (antes que nada: lo demás supone país, regiones y Montevideo)
    fuera = obs[~nivel.isin(NIVELES) | ((nivel == "departamento") & (obs.territorio_id != MVD))]
    c.chk("AC-I17 Solo país, regiones y Montevideo", fuera.empty,
          f"{len(fuera)} valores en {sorted(set(fuera.territorio_id))[:5]}" if len(fuera) else "")

    no_positivos = obs[~(obs.valor > 0)]
    c.chk("AC-I12 Todos los valores son mayores que 0", no_positivos.empty,
          _ejemplos(no_positivos[["indicador", "territorio_id", "periodo", "valor"]]))

    w = obs.pivot_table(index=["territorio_id", "periodo"], columns="indicador", values="valor", aggfunc="first")
    _orden(c, w, "AC-I13 Per cápita menor que hogar",
           [(f"ing_hogar_medio_{v}", f"ing_pc_medio_{v}", True) for v in VARIANTES])
    _orden(c, w, "AC-I13 Con aguinaldo ≥ sin aguinaldo",
           [(f"ing_{m}_medio_cagu_{vl}", f"ing_{m}_medio_sagu_{vl}", False) for m in ("hogar", "pc") for vl in ("cvl", "svl")])
    _orden(c, w, "AC-I13 Con valor locativo ≥ sin valor locativo",
           [(f"ing_{m}_medio_{a}_cvl", f"ing_{m}_medio_{a}_svl", False) for m in ("hogar", "pc") for a in ("cagu", "sagu")])

    t = obs.pivot_table(index=["indicador", "periodo"], columns="territorio_id", values="valor", aggfunc="first")
    for nombre, x, a, b in [("AC-I14 El Interior está entre sus dos partes", INTERIOR, I5000, MENORES),
                            ("AC-I14 El país está entre Montevideo y el Interior", PAIS, MVD, INTERIOR)]:
        if not {x, a, b} <= set(t.columns):
            c.chk(nombre, False, f"faltan territorios: {sorted({x, a, b} - set(t.columns))}")
            continue
        y = t[[x, a, b]].dropna()
        bajo, alto = y[[a, b]].min(axis=1), y[[a, b]].max(axis=1)
        mal = y[(y[x] < bajo - TOLERANCIA) | (y[x] > alto + TOLERANCIA)]
        c.chk(nombre, mal.empty, f"{len(mal)} casos: {list(mal.index[:3])}" if len(mal) else "")

    # AC-I16 por indicador y territorio
    q = obs[obs.tipo_periodo == "trimestre"].assign(anio=lambda d: d.periodo.str[:4].astype(int),
                                                    n=lambda d: d.periodo.str[-1].astype(int))
    a = obs[obs.tipo_periodo == "anio"].assign(anio=lambda d: d.periodo.astype(int))
    problemas = []
    for (ind, ter), g in q.groupby(["indicador", "territorio_id"]):
        por_anio = g.groupby("anio").n.apply(sorted)
        totales = set(a[(a.indicador == ind) & (a.territorio_id == ter)].anio)
        ultimo = max(por_anio.index)
        completo = ultimo if por_anio[ultimo] == [1, 2, 3, 4] else ultimo - 1
        for anio in range(PRIMER_ANIO, completo + 1):
            if por_anio.get(anio) != [1, 2, 3, 4] or anio not in totales:
                problemas.append(f"{ind} {ter} {anio}")
        if completo < ultimo and (por_anio[ultimo] != list(range(1, len(por_anio[ultimo]) + 1)) or ultimo in totales):
            problemas.append(f"{ind} {ter} {ultimo} (año en curso)")
        if min(por_anio.index) < PRIMER_ANIO or totales - set(range(PRIMER_ANIO, completo + 1)):
            problemas.append(f"{ind} {ter}: años fuera de {PRIMER_ANIO}–{completo}")
    c.chk(f"AC-I16 Cada año desde {PRIMER_ANIO} con 4 trimestres y su total; el año en curso sin total",
          not problemas, f"{len(problemas)} casos: {problemas[:3]}" if problemas else "")

    # AC-I15 (advertencia)
    prom = q.groupby(["indicador", "territorio_id", "anio"]).valor.agg(["mean", "size"])
    prom = prom[prom["size"] == 4]["mean"]
    m = a.set_index(["indicador", "territorio_id", "anio"]).valor.to_frame().join(prom, how="inner")
    lejos = m[(m.valor / m["mean"] - 1).abs() > TOLERANCIA_TOTAL]
    advertencias += [f"{i} {ter} {anio}: total {v:,.0f} y promedio de los trimestres {p:,.0f}".replace(",", ".")
                     for (i, ter, anio), v, p in zip(lejos.index, lejos.valor, lejos["mean"])]
    return c, advertencias


def ultimos_valores(obs: pd.DataFrame) -> list[str]:
    """Tabla del último trimestre de los dos indicadores titulares del INE (sin aguinaldo, sin valor locativo)."""
    titulares = ["ing_hogar_medio_sagu_svl", "ing_pc_medio_sagu_svl"]
    q = obs[(obs.tipo_periodo == "trimestre") & obs.indicador.isin(titulares)]
    if q.empty:
        return []
    ultimo = max(q.periodo)
    x = q[q.periodo == ultimo].pivot_table(index="territorio_id", columns="indicador", values="valor")
    orden = [PAIS, MVD, INTERIOR, I5000, MENORES]
    nombres = {PAIS: "Total país", MVD: "Montevideo", INTERIOR: "Interior", I5000: "Interior: 5.000 o más",
               MENORES: "Interior: pequeñas y rurales"}

    def f(v):
        return "—" if pd.isna(v) else f"{v:,.0f}".replace(",", ".")

    return [f"Últimos valores ({ultimo}, pesos corrientes por mes, sin aguinaldo ni valor locativo):", "",
            "| Territorio | Ingreso medio de los hogares | Per cápita |", "|---|---:|---:|",
            *[f"| {nombres[t]} | {f(x.at[t, titulares[0]] if t in x.index and titulares[0] in x else None)} | "
              f"{f(x.at[t, titulares[1]] if t in x.index and titulares[1] in x else None)} |" for t in orden]]
