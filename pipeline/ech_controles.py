"""F2.6: controles de calidad del mercado de trabajo (ECH) y su sección del reporte de validación.

Sobre las observaciones de todos los informes vigentes (formato largo: territorio_id, periodo, indicador, valor):

- AC-L12  tasas entre 0 y 100; tasa de empleo ≤ tasa de actividad.                       Falla.
- AC-L13  activos − ocupados = desocupados, ±1 mil (redondeo).                            Falla.
- AC-L14  desocupados / activos × 100 = tasa de desempleo, ±0,3 puntos.                   Advertencia:
          en departamentos chicos el redondeo de los miles a un decimal mueve el cociente más que eso
          (decisión del mantenedor, opción c, #45).
- AC-L15  por informe: 19 departamentos y 8 municipios, a lo sumo un país, 7 indicadores
          por territorio y nada repetido.                                                  Falla.
- AC-L16  ningún valor en sección, segmento, localidad, barrio ni CCZ.                     Falla.
"""

from __future__ import annotations

import pandas as pd
from territorios_2023 import NOMBRES_DEPTO

from comun.controles import Controles

TASAS = ["tasa_actividad", "tasa_empleo", "tasa_desempleo", "tasa_no_registro"]
INDICADORES = 7
NIVELES_PROHIBIDOS = {"seccion", "segmento", "localidad", "barrio_mvd", "ccz_mvd"}
TOLERANCIA_MILES = 1.0
TOLERANCIA_DESEMPLEO = 0.3
PRIMER_MES = (2022, 2)


def ancho(obs: pd.DataFrame) -> pd.DataFrame:
    """Una fila por informe y territorio, una columna por indicador."""
    return obs.pivot_table(index=["periodo", "territorio_id"], columns="indicador", values="valor",
                           aggfunc="first").reset_index()


def nombre(territorio_id: str) -> str:
    _, nivel, codigo = territorio_id.split("/")
    return {"departamento": NOMBRES_DEPTO.get(codigo, codigo), "pais": "Total país"}.get(nivel, f"Municipio {codigo}")


def num(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def controles(obs: pd.DataFrame) -> tuple[Controles, list[str]]:
    c, advertencias = Controles(), []
    nivel = obs.territorio_id.str.split("/").str[1]

    # AC-L16 (antes que nada: el resto supone solo país, departamentos y municipios)
    prohibidos = sorted(set(nivel) & NIVELES_PROHIBIDOS)
    c.chk("AC-L16 Sin valores en sección, segmento, localidad, barrio ni CCZ", not prohibidos,
          ", ".join(prohibidos) or "niveles: " + ", ".join(sorted(set(nivel))))

    # AC-L15
    repetidas = int(obs.duplicated(["territorio_id", "periodo", "indicador"]).sum())
    por_informe = obs.assign(nivel=nivel).groupby("periodo")
    malos = []
    for periodo, g in por_informe:
        cuenta = g.drop_duplicates("territorio_id").nivel.value_counts()
        if cuenta.get("departamento", 0) != 19 or cuenta.get("municipio_mvd", 0) != 8 or cuenta.get("pais", 0) > 1:
            malos.append(f"{periodo}: {dict(cuenta)}")
        incompletos = g.groupby("territorio_id").indicador.nunique()
        if (incompletos != INDICADORES).any():
            malos.append(f"{periodo}: {list(incompletos[incompletos != INDICADORES].index)[:3]} sin los 7 indicadores")
    c.chk("AC-L15 Por informe: 19 departamentos, 8 municipios, a lo sumo un país, 7 indicadores, nada repetido",
          not malos and not repetidas,
          "; ".join(malos[:5]) + (f"; {repetidas} repetidas" if repetidas else "") or f"{obs.periodo.nunique()} informes")

    w = ancho(obs)
    # AC-L12
    fuera = w[(w[TASAS] < 0).any(axis=1) | (w[TASAS] > 100).any(axis=1)]
    empleo = w[w.tasa_empleo > w.tasa_actividad]
    c.chk("AC-L12 Tasas entre 0 y 100; empleo ≤ actividad", fuera.empty and empleo.empty,
          f"{len(fuera)} fuera de 0–100, {len(empleo)} con empleo > actividad"
          + (f" (p. ej. {nombre(empleo.iloc[0].territorio_id)} {empleo.iloc[0].periodo})" if len(empleo) else ""))

    # AC-L13
    dif = (w.activos - w.ocupados - w.desocupados).abs()
    c.chk(f"AC-L13 Activos − ocupados = desocupados (±{num(TOLERANCIA_MILES)} mil)",
          (dif <= TOLERANCIA_MILES + 1e-9).all(),
          f"diferencia máxima {num(dif.max())} mil" + (f" ({nombre(w.loc[dif.idxmax()].territorio_id)} "
                                                        f"{w.loc[dif.idxmax()].periodo})" if len(w) else ""))

    # AC-L14 (advertencia)
    calc = w.desocupados / w.activos * 100
    d = (calc - w.tasa_desempleo).abs()
    lejos = w[d > TOLERANCIA_DESEMPLEO + 1e-9]
    for i, r in lejos.iterrows():
        advertencias.append(f"{r.periodo} · {nombre(r.territorio_id)}: desocupados / activos = "
                            f"{num(r.desocupados)} / {num(r.activos)} = {calc[i]:.2f} % y tasa publicada "
                            f"{num(r.tasa_desempleo)} % (diferencia {d[i]:.2f})".replace(".", ","))
    c.chk(f"AC-L14 Desocupados / activos × 100 = tasa de desempleo (±{num(TOLERANCIA_DESEMPLEO)}; si no, advertencia)",
          True, f"{len(lejos)} fuera de ±{num(TOLERANCIA_DESEMPLEO)} (advertencias; diferencia máxima {num(d.max())})")
    return c, advertencias


def meses(desde: tuple[int, int], hasta: tuple[int, int]) -> list[str]:
    (a, m), salida = desde, []
    while (a, m) <= hasta:
        salida.append(f"{a}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return salida


def seccion_reporte(obs: pd.DataFrame, registro: list[dict], c: Controles, advertencias: list[str],
                    redondeo: list[tuple[str, str]]) -> list[str]:
    """AC-L21: meses capturados y faltantes, controles y últimos valores por departamento."""
    vigentes = sorted({x["periodo"] for x in registro if x["vigente"]}, key=lambda p: p[-7:])
    finales = [p[-7:] for p in vigentes]
    ultimo = tuple(map(int, finales[-1].split("-"))) if finales else PRIMER_MES
    faltan = [m for m in meses(PRIMER_MES, ultimo) if m not in finales]
    lineas = ["## Mercado de trabajo (ECH)", "",
              f"Meses capturados: {len(vigentes)} ({finales[0] if finales else '—'} a {finales[-1] if finales else '—'}, "
              f"por mes final del trimestre móvil); faltan: {', '.join(faltan) or 'ninguno'}. "
              f"Capturas en el registro: {len(registro)} (vigentes: {sum(x['vigente'] for x in registro)}).", "",
              "### Controles", "", *c.tabla_md(), ""]
    lineas += ["### Advertencias", ""]
    lineas += [f"- Desempleo calculado (AC-L14) · {a}" for a in advertencias]
    lineas += [f"- «Total Montevideo» (redondeo aceptado, hasta 0,1) · `{archivo}`: {d}" for archivo, d in redondeo]
    if not advertencias and not redondeo:
        lineas.append("- Ninguna.")
    if vigentes:
        w = ancho(obs[obs.periodo == vigentes[-1]])
        w = w[w.territorio_id.str.contains("/departamento/|/pais/")].sort_values("territorio_id")
        lineas += ["", f"### Últimos valores por departamento ({vigentes[-1]})", "",
                   "| Territorio | Actividad (%) | Empleo (%) | Desempleo (%) | No registro (%) |", "|---|---:|---:|---:|---:|"]
        lineas += [f"| {nombre(r.territorio_id)} | {num(r.tasa_actividad)} | {num(r.tasa_empleo)} | "
                   f"{num(r.tasa_desempleo)} | {num(r.tasa_no_registro)} |" for r in w.itertuples()]
    return lineas
