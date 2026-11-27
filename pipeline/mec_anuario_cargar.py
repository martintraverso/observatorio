"""F4.4 (#167): carga de los anuarios del MEC en las tablas del observatorio (AC-E4…E7, AC-E16).

Lee el registro de capturas (`<crudo>/mec_anuario/capturas.json`, de `mec_anuario_captura.py`) y, de cada anuario
vigente, los cuadros de la ola 1 con el mapeo por columna del registro de la fuente (`pipeline/mec_anuario.py`).
Escribe lo de la fuente en `<salida>/fuentes/mec_anuario_educacion/` y arma las tablas compartidas con
`comun.salida.combinar`, como la carga de ingresos (F3.4b):

- Cada año es una captura (AC-E4). Una captura ya cargada (mismo sha256) no se vuelve a parsear (AC-P8); una
  nueva reemplaza los valores de su año y el reporte dice cuántos cambiaron y el cambio más grande (AC-E6). Un
  cambio en el mapeo del registro no recarga lo ya cargado: hace falta --forzar (como en ingresos).
- Un año con error de descarga queda en el reporte y los demás se cargan igual (AC-E5).
- La serie nacional 2002–<año> sale del anuario más reciente; donde se superpone con un cuadro anual se guardan los
  dos y una diferencia es advertencia (AC-E7).
- Tasas derivadas (D2, AC-E16), con numerador y denominador del mismo cuadro, año, territorio y alcance:
  tasa de promoción = promovidos / (promovidos + no promovidos) × 100 en cada cuadro de rendimiento, y % de
  matrícula privada = privada / total × 100 en II-2.2.1. Cada una es un indicador propio con `es_derivado` y su
  `formula`. El % de asistencia insuficiente no se calcula: II-2.2.18 no trae la matrícula (mantenedor, 2026-11-23).

Uso: python pipeline/mec_anuario_cargar.py datos/crudo/mec_anuario [--salida datos/salida] [--fuentes fuentes/] [--forzar]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import mec_anuario as mec
import mec_ine_control
import pandas as pd
import yaml
from ech_ingresos_captura import leer_completo, verificar
from ech_ingresos_cargar import _num, resumen_cambios
from mec_anuario_captura import CARPETA, FUENTE_ID
from mec_anuario_controles import controles, lineas_saltos

from comun.capturas import Historial, ahora, nueva_captura
from comun.registro import RAIZ, cargar_fuentes
from comun.salida import carpeta_fuente, combinar, escribir_fuente

CLAVE = ["indicador", "territorio_id", "periodo"]
TEMA = "Educación"
MARCA, FIN = "<!-- mec_anuario -->", "<!-- /mec_anuario -->"
DERIVADO = re.compile(r"_tasa_promocion|_pct_privada")
# AC-E7: indicadores de la serie nacional que repiten un valor de un cuadro anual (país)
SOLAPES = {
    "edu_serie_total_educacion_primaria_primaria_comun": "edu_ii_2_2_1_total",
    "edu_serie_total_educacion_primaria_primaria_comun_comun_publica": "edu_ii_2_2_1_forma_de_administracion_publica_total",
    "edu_serie_total_educacion_primaria_primaria_comun_comun_privada": "edu_ii_2_2_1_forma_de_administracion_privada_total",
}
PCT_PRIVADA = [("edu_ii_2_2_1_pct_privada", "edu_ii_2_2_1_forma_de_administracion_privada_total", "edu_ii_2_2_1_total",
                "Matrícula de primaria común: % en privada")]


class ErrorCarga(ValueError):
    pass


# ---------------------------------------------------------------- lectura de los anuarios

def leer_anuario(xlsx: bytes, anio: int, fuente: dict, sin_dato: set | None = None,
                 categorias: dict | None = None) -> tuple[pd.DataFrame, dict, list[str]]:
    """Valores de los cuadros de la ola 1 de un anuario, con sus pies y avisos por cuadro. Si se pasa `sin_dato`,
    le agrega las celdas publicadas sin dato (indicador, territorio, período), para AC-E21; si se pasa `categorias`,
    el rótulo original de cada categoría de los cuadros B y C (#213)."""
    partes, pies, avisos = [], {}, []
    for cod, e in fuente["cuadros"].items():
        mapeo = (e.get("mapeo") or {}).get(anio)
        if e.get("ola") != 1 or not mapeo:
            continue
        c = mec.parsear_cuadro(xlsx, cod, anio, mapeo, e["tipos"][anio], (e.get("categorias_segundas") or {}).get(anio, ()),
                               e.get("secciones_por_institucion"), e.get("solo_filas") or (),
                               e.get("filas_de_establecimiento"), e.get("rotulos_de_fila"), e.get("grupos_por_fila") or (),
                               bool(e.get("solo_enteros")))
        partes.append(c.datos)
        if sin_dato is not None:
            sin_dato.update(c.sin_dato_claves)
        if categorias is not None:
            categorias.update(c.categorias)
        pies[cod] = c.pie
        avisos += c.avisos + ([f"{cod} {anio}: {c.sin_dato} celdas sin dato («-», «s/d», vacías)"] if c.sin_dato else [])
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=mec.COLUMNAS), pies, avisos


def reglas_sin_cargar(reglas: dict, cod: str | None, indicador: str) -> list[dict]:
    """#233: las reglas de `observaciones_sin_cargar` que alcanzan a un indicador (columna por `patron` en el id base;
    las categorías de `salvo` se cargan). Un cuadro puede tener una regla o una lista (#241)."""
    r = reglas.get(cod) if cod else None
    base, _, categoria = indicador.partition("__")
    return [x for x in (r if isinstance(r, list) else [r] if r else [])
            if x["patron"] in base and categoria not in x.get("salvo", [])
            and (not x.get("categorias") or categoria in x["categorias"])]  # #255: solo esas categorías


def regla_sin_cargar(reglas: dict, cod: str | None, indicador: str) -> dict | None:
    """La primera regla de `reglas_sin_cargar`, o None."""
    return next(iter(reglas_sin_cargar(reglas, cod, indicador)), None)


def quitar_sin_cargar(obs: pd.DataFrame, reglas: dict, cuadro_de: dict, sin_dato: set | None = None) -> pd.DataFrame:
    """#233 (mantenedor): saca los valores publicados que no se cargan (`observaciones_sin_cargar`, por cuadro, años,
    columna, categoría y, si la regla los dice, territorios: #241), p. ej. las horas por asignatura de II-3.3.1 en 2020
    y 2021, desalineadas en el archivo. Lo que se saca cuenta como publicado sin dato (AC-E21), si se pasa `sin_dato`."""
    if not reglas or obs.empty:
        return obs

    def fuera_de(i, terr, per):
        anio = int(str(per)[:4])
        return any(anio in r["anios"] and (not r.get("territorios") or terr.split("/", 1)[-1] in r["territorios"])
                   for r in reglas_sin_cargar(reglas, cuadro_de.get(i.split("__")[0]), i))

    terr = obs.territorio_id if "territorio_id" in obs else pd.Series("", index=obs.index)
    fuera = pd.Series([fuera_de(i, t, p) for i, t, p in zip(obs.indicador, terr, obs.periodo)], index=obs.index, dtype=bool)
    if sin_dato is not None:
        sin_dato.update((i, t, str(p)) for i, t, p in zip(obs.indicador[fuera], terr[fuera], obs.periodo[fuera]))
    return obs[~fuera].reset_index(drop=True)


def derivados(obs: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Tasas de D2 a partir de los conteos cargados (AC-E16): solo donde están numerador y denominador del mismo
    cuadro (el id lo dice), año, territorio y alcance. Devuelve las observaciones y {indicador: (fórmula, cuadro)}."""
    base = obs[~obs.indicador.str.contains(DERIVADO)]
    por = base.set_index(CLAVE).valor
    filas, formulas = [], {}

    def agregar(nuevo, num, valor_den, formula, ref):
        if valor_den:
            filas.append({**ref, "indicador": nuevo, "valor": float(num) / float(valor_den) * 100})
            formulas[nuevo] = (formula, ref.get("codigo_cuadro") or "")

    for ref in base.to_dict("records"):
        m = re.fullmatch(r"(.*)_no_promovidos?(.*)", ref["indicador"])
        if m:  # «no promovidos» y su par «promovidos» del mismo cuadro y alcance
            pre, suf = m.groups()
            plural = ref["indicador"][len(pre):].startswith("_no_promovidos")
            prom = f"{pre}_promovido{'s' if plural else ''}{suf}"
            k = (prom, ref["territorio_id"], ref["periodo"])
            if k in por.index:
                p, n = por[k], ref["valor"]
                agregar(f"{pre}_tasa_promocion{suf}", p, p + n, f"{prom} / ({prom} + {ref['indicador']}) × 100", ref)
        for nuevo, num, den, _ in PCT_PRIVADA:
            if ref["indicador"] == num:
                k = (den, ref["territorio_id"], ref["periodo"])
                if k in por.index:
                    agregar(nuevo, ref["valor"], por[k], f"{num} / {den} × 100", ref)
    d = pd.DataFrame(filas, columns=obs.columns)
    return d, formulas


# Siglas que aparecen en los títulos de los cuadros: quedan en mayúsculas al pasar el título a minúsculas (#213).
SIGLAS = {"ANEP", "CAIF", "CEIP", "CENFORES", "CES", "CETP", "CFE", "CIEP", "DGEIP", "DGES", "DGETP", "INAU", "JICI",
          "FINEST", "MEC", "UDELAR", "UTEC", "UTU"}


def _sigla(palabra: str) -> bool:
    """Una sigla del archivo: de la lista (DGEIP, INAU…) o con puntos («C.B.T.», «E.»)."""
    p = palabra.strip("(),:;")
    return (p.strip(".") in SIGLAS and p.isupper()) or bool(re.fullmatch(r"(?:[A-ZÁÉÍÓÚÑ]\.)+", p))


def legible(texto: str, primera: bool = True) -> str:
    """«ESTUDIANTES … DE LA DGEIP» → «Estudiantes … de la DGEIP»: minúsculas salvo las siglas, sin cambiar palabras."""
    t = " ".join(p if _sigla(p) else p.lower() for p in texto.split(" "))
    return t[:1].upper() + t[1:] if primera else t


def apertura_legible(ruta: str) -> str:
    """«FORMA DE ADMINISTRACIÓN/PRIVADA/SEXO/M» → «forma de administración · privada · sexo · M». Los tramos van
    separados como en el archivo, sin suponer cuál es la dimensión y cuál el valor; un tramo de una letra (M, V) queda
    como está."""
    tramos = [t.strip() for t in ruta.split("/") if t.strip()]
    return " · ".join(t if re.fullmatch(r"\w", t) else legible(t, False) for t in tramos)


def nombre_tasa(cod: str, e: dict, concepto: str, categoria: str = "") -> str:
    """#213: «Tasa de promoción en educación primaria común pública — área demográfica rural». El nivel sale del título
    del cuadro; la apertura, de la ruta del indicador «promovidos» de la fórmula, sin los tramos de rendimiento."""
    m = re.search(r"\bEN (EDUCACI[ÓO]N .+?)(?: POR | SEG[ÚU]N |$)", e.get("titulo", ""))
    donde = legible(m.group(1), False) if m else f"el cuadro {cod}"
    tramos = [t for t in concepto.split("/") if not re.fullmatch(r"(?i)\s*(rendimiento( escolar| educativo)?|promovidos?)\s*", t)]
    tramos = [t for t in tramos if t.strip().upper() != "TOTAL"]
    apertura = apertura_legible("/".join(tramos))
    extra = [x for x in (apertura, legible(categoria, False) if categoria else "") if x]
    return f"Tasa de promoción en {donde}" + (f" — {'; '.join(extra)}" if extra else "")


def indicadores(obs: pd.DataFrame, fuente: dict, pies: dict, formulas: dict, serie: pd.DataFrame,
                notas_prev: dict | None = None, categorias: dict | None = None,
                nombres_prev: dict | None = None, no_aditivos: dict | None = None,
                unidades: dict | None = None) -> pd.DataFrame:
    """El catálogo: nombre, unidad y columna de origen de cada indicador cargado; la nota es el pie del cuadro (del
    año más reciente parseado; si en esta corrida no se parseó, la que ya estaba publicada). El nombre usa la ortografía
    del archivo: el título con sus siglas, y la categoría de los cuadros B y C tal como la escribe el archivo
    (`categorias`; si el año no se parseó en esta corrida, el nombre ya publicado, #213)."""
    categorias, nombres_prev = categorias or {}, nombres_prev or {}
    origen = {}
    for cod, e in fuente["cuadros"].items():
        for anio, m in sorted((e.get("mapeo") or {}).items()):
            for x in m or []:
                origen[x["id"]] = (cod, x.get("concepto", x["ruta"]), e)
    rutas_serie = dict(zip(serie.indicador, serie.ruta)) if len(serie) else {}
    filas = []
    for ind in sorted(obs.indicador.unique()):
        base, _, categoria = ind.partition("__")
        if ind in rutas_serie and ind.startswith("edu_ii_7_2_8_"):  # #269: la serie por institución
            filas.append({"codigo": ind, "nombre": f"Evolución de la matrícula universitaria de grado y posgrado: {rutas_serie[ind]}",
                          "unidad": "estudiantes", "columna_origen": f"Cuadro {mec.SERIE_INSTITUCIONES} · {rutas_serie[ind]}",
                          "nota": " ".join(["Serie del anuario más reciente.", *pies.get(mec.SERIE_INSTITUCIONES, [])]),
                          "es_derivado": False, "formula": ""})
            continue
        if ind in rutas_serie:
            filas.append({"codigo": ind, "nombre": f"Matrícula del sistema educativo: {rutas_serie[ind]}",
                          "unidad": "estudiantes", "columna_origen": f"Hoja {mec.SERIE} · {rutas_serie[ind]}",
                          "nota": "Serie del anuario más reciente.", "es_derivado": False, "formula": ""})
            continue
        if ind in formulas:
            formula, cod = formulas[ind]
            prom = formula.split(" / ")[0].strip()
            pbase, _, pcat = prom.partition("__")
            _, concepto_p, e_p = origen.get(pbase) or (cod, "", {})
            nombre = next((n for i, _, _, n in PCT_PRIVADA if i == ind), None)
            if nombre is None and pcat and prom not in categorias and ind in nombres_prev:
                nombre = nombres_prev[ind]  # año no parseado en esta corrida: el nombre que ya estaba publicado
            if nombre is None:
                nombre = nombre_tasa(cod, e_p, concepto_p, categorias.get(prom, pcat.replace("_", " ")))
            filas.append({"codigo": ind, "nombre": nombre, "unidad": "%", "columna_origen": f"Cuadro {cod} (calculado)",
                          "nota": "Calculado por el observatorio a partir de MEC.", "es_derivado": True,
                          "formula": formula})
            continue
        cod, concepto, e = origen.get(base) or origen.get(re.sub(r"__\d+$", "", base)) or (None, base, {})
        if cod is None:
            raise ErrorCarga(f"Indicador sin origen en el registro: {ind}")
        nombre = legible(re.sub(r"\s*\(Todo el país.*", "", e["titulo"])) + f": {concepto}"
        if categoria:
            if ind in categorias:
                nombre += f" — {categorias[ind]}"
            elif ind in nombres_prev:  # año no parseado en esta corrida: el nombre que ya estaba publicado
                nombre = nombres_prev[ind]
            else:
                nombre += f" — {categoria.replace('_', ' ')}"
        na = (no_aditivos or {}).get(cod)
        un = next((u["unidad"] for u in (unidades or {}).get(cod, []) if u["patron"] in base), None)  # #233: horas
        unidad = na["unidad"] if na and na["patron"] in base else un or e.get("unidad", "estudiantes")  # #225: promedios
        filas.append({"codigo": ind, "nombre": nombre, "unidad": unidad,
                      "columna_origen": f"Cuadro {cod} · {concepto}",
                      "nota": " ".join(pies[cod]) if cod in pies else (notas_prev or {}).get(ind, ""),
                      "es_derivado": False, "formula": ""})
    df = pd.DataFrame(filas)
    # #214: dos tasas de cuadros distintos con el mismo nombre (el total de primaria pública en II-2.2.13, por área, y
    # en II-2.2.14, por sexo) van juntas en la lista del mapa: se distinguen por la apertura del cuadro («por sexo»).
    tasas = df.es_derivado & df.nombre.str.startswith("Tasa de promoción")
    choque = tasas & df.nombre.duplicated(keep=False) & ~df.assign(_c=df.columna_origen).duplicated(["nombre", "_c"], keep=False)

    def por_del_cuadro(origen: str) -> str:
        cod = re.search(r"(II-[\d.]+)", origen)
        m = re.search(r" (POR .+?)(?: SEG[ÚU]N |$)", fuente["cuadros"].get(cod.group(1), {}).get("titulo", "") if cod else "")
        return f" ({legible(m.group(1), False)})" if m else ""

    df.loc[choque, "nombre"] = df.loc[choque, "nombre"] + df.loc[choque, "columna_origen"].map(por_del_cuadro)
    # #213: dos indicadores del mismo cuadro con el mismo nombre (p. ej. la tasa total de II-4.2.14 hasta 2023, que
    # sale de otras columnas que la de 2024) se distinguen por los años que cubren; nunca se supone que son el mismo.
    anios = obs.groupby("indicador").periodo.agg(lambda x: f"{min(x)}–{max(x)}" if min(x) != max(x) else min(x))
    cuadro = df.columna_origen.str.extract(r"(II-[\d.]+)")[0]
    repetido = df.assign(_c=cuadro).duplicated(["_c", "nombre"], keep=False) & cuadro.notna()
    df.loc[repetido, "nombre"] = df.loc[repetido].apply(lambda r: f"{r.nombre} ({anios.get(r.codigo, '')})", axis=1)
    df["tema"], df["fuente_id"] = TEMA, FUENTE_ID
    return df


# ---------------------------------------------------------------- carga

def anteriores(salida: Path):
    if not ((salida / "capturas.parquet").exists() and (salida / "observaciones.parquet").exists()):
        return None, None
    cap = pd.read_parquet(salida / "capturas.parquet")
    cap = cap[cap.fuente_id == FUENTE_ID]
    if cap.empty:
        return None, None
    obs = pd.read_parquet(salida / "observaciones.parquet")
    return obs[obs.captura_id.isin(cap.id)], cap


def publicar(salida: Path, fuentes: dict, obs, capturas, ind) -> None:
    d = carpeta_fuente(salida, FUENTE_ID)
    antes = {p.name: p.read_bytes() for p in d.glob("*.parquet")} if d.exists() else {}
    escribir_fuente(salida, FUENTE_ID, obs, capturas, ind)
    try:
        combinar(salida, fuentes)
    except Exception:
        for p in d.glob("*.parquet"):
            if p.name in antes:
                p.write_bytes(antes[p.name])
            else:
                p.unlink()
        if not antes:
            d.rmdir()
        raise


def solapes(obs: pd.DataFrame) -> list[str]:
    """AC-E7: la serie y el cuadro anual dicen lo mismo para el país; una diferencia es advertencia."""
    pais = obs[obs.territorio_id == mec.PAIS].set_index(["indicador", "periodo"]).valor
    avisos = []
    for s, c in SOLAPES.items():
        for (ind, per), v in pais[pais.index.get_level_values(0) == s].items():
            otro = pais.get((c, per))
            if otro is not None and otro != v:
                avisos.append(f"{per}: la serie nacional dice {_num(v)} y {c} dice {_num(otro)}")
    return avisos


def cargar(crudo: Path, salida: Path, fuentes: dict, forzar: bool = False, fuentes_dir: Path = RAIZ / "fuentes") -> dict:
    crudo, salida = Path(crudo), Path(salida)
    fuente = fuentes[FUENTE_ID]
    contenido = leer_completo(crudo, CARPETA)
    registro = contenido["capturas"]
    if not registro:
        raise ErrorCarga(f"No hay capturas en {crudo / CARPETA / 'capturas.json'}")
    for c in registro:
        verificar(crudo, c)
    vigentes = sorted((c for c in registro if c["vigente"]), key=lambda c: int(c["codigo"]))
    if not vigentes:
        raise ErrorCarga("No hay capturas vigentes")
    obs_prev, cap_prev = anteriores(salida)
    sin_cambios = (not forzar and cap_prev is not None
                   and sorted(zip(cap_prev.id, cap_prev.vigente)) == sorted((c["id"], c["vigente"]) for c in registro))
    manual_path = Path(fuentes_dir) / "mec_anuario" / "mapeo_manual.yml"
    manual = yaml.safe_load(manual_path.read_text(encoding="utf-8")) if manual_path.exists() else {}
    archivos = {int(c["codigo"]): (crudo / c["archivo"]).read_bytes() for c in vigentes}
    hay_interior = _hay_interior(salida)
    if sin_cambios:  # AC-P8: nada nuevo, no se vuelve a parsear ni a publicar; el reporte sale de lo publicado
        i_prev = pd.read_parquet(salida / "indicadores.parquet")
        deriv_prev = set(i_prev[(i_prev.fuente_id == FUENTE_ID) & i_prev.es_derivado].codigo)
        return {"resultado": "sin cambios", "capturas": len(registro), "vigentes": len(vigentes), "parseadas": 0,
                "_registro": registro, "_ultima": contenido.get("ultima_corrida") or {}, "_obs": obs_prev,
                "_revision": controles(obs_prev, fuente, manual, deriv_prev, set(), set(), hay_interior),
                "_fuente": fuente, "_faltantes": faltantes(fuente, archivos),
                "_ine": control_ine(crudo, obs_prev, deriv_prev, manual)}

    # AC-E6 / AC-P8: una captura ya cargada (mismo sha256) no se vuelve a parsear; sus valores se toman de lo
    # publicado. La serie y las tasas se recalculan sobre el conjunto.
    ya = set() if forzar or obs_prev is None else set(obs_prev.captura_id)
    cuadro_de = {x["id"]: cod for cod, e in fuente["cuadros"].items() for m in (e.get("mapeo") or {}).values()
                 for x in m or []}
    anios_vigentes = [int(c["codigo"]) for c in vigentes]
    ultimo_de = {cod: max((a for a in anios_vigentes if (e.get("mapeo") or {}).get(a)), default=None)
                 for cod, e in fuente["cuadros"].items()}
    partes, pies, avisos, parseadas, sin_dato, categorias_anio = [], {}, [], [], set(), {}
    for c in vigentes:
        anio = int(c["codigo"])
        if c["id"] in ya:
            previas = obs_prev[(obs_prev.captura_id == c["id"]) & ~obs_prev.indicador.str.contains(DERIVADO)
                               & ~obs_prev.indicador.str.startswith(("edu_serie_", "edu_ii_7_2_8_"))]  # se rehacen (#269)
            partes.append(previas.drop(columns=["es_estimado"], errors="ignore").assign(
                codigo_cuadro=previas.indicador.str.split("__").str[0].map(cuadro_de), celda=""))
            continue
        cats: dict = {}
        datos, p, a = leer_anuario((crudo / c["archivo"]).read_bytes(), anio, fuente, sin_dato, cats)
        # #224: el rótulo de cada categoría, del año más nuevo que se parsea
        for k, v in cats.items():
            if anio >= categorias_anio.get(k, (0, ""))[0]:
                categorias_anio[k] = (anio, v)
        partes.append(datos.assign(captura_id=c["id"]))
        # la nota de un indicador es el pie del cuadro en el anuario más reciente que lo trae: un año viejo
        # parseado (una revisión de 2022) no la cambia
        pies.update({cod: pie for cod, pie in p.items() if anio == ultimo_de.get(cod)})
        avisos += a
        parseadas.append(c["id"])
    ultimo = vigentes[-1]
    serie = mec.parsear_serie_matricula((crudo / ultimo["archivo"]).read_bytes()).assign(captura_id=ultimo["id"])
    # #269 (mantenedor en #243): II-7.2.8, la serie por institución, solo del anuario más reciente
    inst = mec.parsear_serie_instituciones((crudo / ultimo["archivo"]).read_bytes(), int(ultimo["codigo"]))
    pies[mec.SERIE_INSTITUCIONES] = inst.attrs["pie"]
    inst = inst.assign(captura_id=ultimo["id"])
    cuadro_de["edu_ii_7_2_8_matricula"] = mec.SERIE_INSTITUCIONES
    serie = pd.concat([serie, inst], ignore_index=True)
    obs = pd.concat([*partes, serie.drop(columns=["ruta"])], ignore_index=True)
    sin_cargar = manual.get("observaciones_sin_cargar") or {}
    obs = quitar_sin_cargar(obs, sin_cargar, cuadro_de, sin_dato)
    deriv, formulas = derivados(obs)
    # F4.5a: controles antes de publicar; una falla frena la carga
    anios_parseados = {c["codigo"] for c in vigentes if c["id"] in parseadas}
    revision = controles(pd.concat([obs, deriv], ignore_index=True), fuente, manual, set(formulas), sin_dato,
                         anios_parseados, hay_interior)
    if revision.controles.fallas:
        raise ErrorCarga("Controles de calidad con falla: " + "; ".join(
            f"{f['control']} ({f['detalle']})" for f in revision.controles.fallas))
    if not hay_interior:  # AC-E18: sin el territorio, ninguna fila del Interior (tampoco las B bajo «TOTAL RESTO…»)
        obs = obs[obs.territorio_id != mec.INTERIOR].reset_index(drop=True)
        deriv, formulas = derivados(obs)
    elif revision.region_salteada:  # AC-E18: sin la fila del Interior donde no es TOTAL − MONTEVIDEO
        saltear = pd.MultiIndex.from_tuples(sorted(revision.region_salteada))
        clave = pd.MultiIndex.from_arrays([obs.indicador, obs.periodo])
        obs = obs[~((obs.territorio_id == mec.INTERIOR) & clave.isin(saltear))].reset_index(drop=True)
        deriv, formulas = derivados(obs)
    obs = pd.concat([obs, deriv], ignore_index=True)
    if obs.duplicated(CLAVE).any():
        raise ErrorCarga("Valores repetidos para el mismo indicador, territorio y período: "
                         f"{obs[obs.duplicated(CLAVE, keep=False)][CLAVE].head(3).to_dict('records')}")
    nivel = obs.territorio_id.str.split("/").str[1]
    fuera = sorted(set(nivel) - set(fuente["niveles_publicados"]))
    if fuera:
        raise ErrorCarga(f"Observaciones en niveles que la fuente no publica: {fuera}")  # AC-P5
    notas_prev, nombres_prev = {}, {}
    if (salida / "indicadores.parquet").exists():
        i_prev = pd.read_parquet(salida / "indicadores.parquet")
        i_prev = i_prev[i_prev.fuente_id == FUENTE_ID]
        notas_prev, nombres_prev = dict(zip(i_prev.codigo, i_prev.nota)), dict(zip(i_prev.codigo, i_prev.nombre))
    # #224: el rótulo vale solo si viene del anuario más nuevo que publica el indicador; si ese no se parseó en esta
    # corrida (revisión de un año viejo), queda el nombre ya publicado (AC-E6: igual que una carga completa).
    anio_de_captura = {c["id"]: int(c["codigo"]) for c in vigentes}
    ultimo_anio = obs.assign(_a=obs.captura_id.map(anio_de_captura)).groupby("indicador")._a.max()
    categorias = {k: v for k, (a, v) in categorias_anio.items() if a >= ultimo_anio.get(k, a)}
    ind = indicadores(obs, fuente, pies, formulas, serie, notas_prev, categorias, nombres_prev, manual.get("no_aditivos"),
                      manual.get("unidades"))
    # #233: la nota de lo que no se carga dice qué años faltan y por qué (AC-E2); #173: y la nota del cuadro que el
    # mantenedor agrega (`notas_cuadro`)
    notas_cuadro, notas_indicador = manual.get("notas_cuadro") or {}, manual.get("notas_indicador") or {}
    for k, i in enumerate(ind.codigo):
        base = i.split("__")[0]
        extras = [r["motivo"] for r in reglas_sin_cargar(sin_cargar, cuadro_de.get(base), i)]
        extras += [notas_cuadro[c]] if (c := cuadro_de.get(base)) in notas_cuadro else []
        extras += [notas_indicador[base]] if base in notas_indicador else []  # #241
        for extra in extras:
            if extra not in ind.at[k, "nota"]:
                previa = ind.at[k, "nota"].strip()
                ind.at[k, "nota"] = (previa + ("" if not previa or previa.endswith(".") else ".") + " " + extra).strip()
    hoy = ahora()
    fecha_prev = {} if cap_prev is None else dict(zip(cap_prev.id, cap_prev.fecha_proceso))
    capturas = [nueva_captura(FUENTE_ID, c["archivo"], c["sha256"], hoy if c["id"] in parseadas else fecha_prev.get(c["id"], hoy),
                              url=c["url"], descargado=c["descargado"], vigente=c["vigente"]) for c in registro]
    cambios = resumen_cambios(obs_prev, obs[CLAVE + ["valor"]])
    publicar(salida, fuentes, obs.drop(columns=["codigo_cuadro", "celda"]).assign(es_estimado=False), capturas, ind)
    return {"resultado": "reprocesado" if forzar else "nuevo", "capturas": len(registro), "vigentes": len(vigentes),
            "parseadas": len(parseadas), "observaciones": len(obs), "derivadas": len(deriv), "cambios": cambios,
            "_registro": registro, "_ultima": contenido.get("ultima_corrida") or {}, "_obs": obs, "_avisos": avisos,
            "_solapes": solapes(obs), "_capturas": capturas, "_parseadas": parseadas, "_revision": revision,
            "_fuente": fuente, "_faltantes": faltantes(fuente, archivos), "_ine": control_ine(crudo, obs, set(formulas), manual)}


# ---------------------------------------------------------------- reporte

def seccion_reporte(r: dict) -> list[str]:
    lineas = ["## Educación (MEC, Anuario Estadístico de Educación)", "",
              "| Año | Capturado | sha256 | Valores |", "|---|---|---|---:|"]
    obs = r.get("_obs")
    for c in sorted((c for c in r["_registro"] if c["vigente"]), key=lambda c: int(c["codigo"])):
        n = int((obs.captura_id == c["id"]).sum()) if obs is not None else "—"
        lineas.append(f"| {c['codigo']} | {c['descargado']} | `{c['sha256'][:12]}` | {n} |")
    errores = r["_ultima"].get("errores", [])
    lineas += ["", f"Última captura: {r['_ultima'].get('fecha', '—')}. "
               + ("Años con error (no se actualizaron; si ya tenían una captura, siguen sus valores):" if errores
                  else "Ningún año con error.")]
    lineas += [f"- **{e['codigo']}**: {e['error']} ({e['url']})" for e in errores]
    if r["resultado"] == "sin cambios":
        return lineas + ["", "Sin capturas nuevas: no se volvió a cargar. Controles, cuadros y últimos valores sobre lo "
                         "ya publicado (AC-E21 se prueba al parsear)."] + _controles_reporte(r)
    cambios = r["cambios"]
    texto = f"{cambios['cambiaron']} valores cambiaron respecto de lo publicado"
    if cambios["mayor"]:
        m = cambios["mayor"]
        texto += f"; el cambio más grande: `{m['indicador']}`, {m['territorio_id']}, {m['periodo']}: {_num(m['antes'])} → {_num(m['ahora'])}"
    lineas += ["", f"Cambios: {texto}. Valores nuevos: {cambios['nuevos']}. Valores que ya no vienen: {cambios['quitados']}.",
               f"Tasas calculadas por el observatorio: {r['derivadas']}.", "",
               f"Serie nacional contra cuadros anuales (AC-E7): {len(r['_solapes'])} diferencias.",
               *[f"- {a}" for a in r["_solapes"]], "", f"Avisos de lectura (celdas salteadas y otros): {len(r['_avisos'])}.",
               *[f"- {a}" for a in r["_avisos"]]]
    return lineas + _controles_reporte(r)


def _controles_reporte(r: dict) -> list[str]:
    revision, obs = r["_revision"], r["_obs"]
    return ["", "### Controles (AC-E17…AC-E22)", "", *revision.controles.tabla_md(), "",
            f"Advertencias (no frenan la carga: excepciones de la fuente con su motivo y filas del Interior "
            f"salteadas): {len(revision.advertencias)}.", *[f"- {a}" for a in revision.advertencias], "",
            *lineas_saltos(revision.saltos), "", *mec_ine_control.lineas_reporte(*r["_ine"]), "",
            *cuadros_reporte(r["_fuente"], r["_faltantes"]), "", *ultimos_valores(obs)]


def control_ine(crudo: Path, obs: pd.DataFrame, porcentajes: set[str], manual: dict) -> tuple[dict | None, dict]:
    """AC-E23: compara con las tablas del INE si están guardadas; nunca carga sus valores."""
    ine, manifiesto = mec_ine_control.leer_capturadas(crudo)
    if ine is None:
        return None, manifiesto
    return mec_ine_control.comparar(ine, obs, manual.get("control_ine") or {}, porcentajes), manifiesto


def _hay_interior(salida: Path) -> bool:
    """AC-E18: sin el territorio region/interior (F3.2), las filas de «RESTO DEL PAÍS» se saltean."""
    p = salida / "territorios.parquet"
    if not p.exists():
        return True
    return bool((pd.read_parquet(p, columns=["id"]).id == mec.INTERIOR).any())


def faltantes(fuente: dict, archivos: dict[int, bytes]) -> list[str]:
    """AC-E24: cuadros de un anuario que el registro no tiene, y cuadros-año mapeados que el anuario no trae."""
    salida = []
    for anio, xlsx in sorted(archivos.items()):
        hojas = {h.strip() for h in mec.nombres_de_hojas(xlsx) if re.fullmatch(r"\s*II-\d+\.\d+\.\d+\s*", h)}
        registrados = {c for c, e in fuente["cuadros"].items() if anio in e.get("anios", [])}
        salida += [f"{c} {anio}: está en el anuario y no en el registro" for c in sorted(hojas - set(fuente["cuadros"]))]
        salida += [f"{c} {anio}: el registro lo mapea y el anuario no lo trae" for c in sorted(registrados - hojas)
                   if (fuente["cuadros"][c].get("mapeo") or {}).get(anio)]
    return salida


def cuadros_reporte(fuente: dict, faltan: list[str]) -> list[str]:
    """AC-E24: cuadros mapeados (se cargan), listados sin carga (ola 2 o con motivo) y faltantes."""
    cuadros = fuente["cuadros"]
    mapeados = sorted(c for c, e in cuadros.items() if e.get("ola") == 1 and any((e.get("mapeo") or {}).values()))
    sin_carga = {c: e for c, e in cuadros.items() if c not in mapeados}
    motivos = collections.Counter("ola 2 (F4.8)" if e.get("ola") == 2 else "sin mapeo" for e in sin_carga.values())
    salteados = [f"{c} {a}: {m}" for c, e in cuadros.items() for a, m in (e.get("sin_cargar") or {}).items()]
    return ["### Cuadros (AC-E24)", "", f"Mapeados y cargados (ola 1): {len(mapeados)}. Listados sin carga: "
            f"{len(sin_carga)} ({', '.join(f'{n} {k}' for k, n in motivos.items())}). Faltantes: {len(faltan)}.",
            *[f"- {f}" for f in faltan],
            *([f"Cuadros-año de la ola 1 sin cargar: {'; '.join(salteados)}."] if salteados else [])]


ULTIMOS = [("edu_serie_total_sistema", "Matrícula total del sistema (serie)"),
           ("edu_ii_2_2_1_total", "Matrícula de primaria común (II-2.2.1)"),
           ("edu_ii_2_2_13_rendimiento_escolar_tasa_promocion_total", "Tasa de promoción en primaria pública (%)")]


def ultimos_valores(obs: pd.DataFrame) -> list[str]:
    """AC-E24: el último valor de algunos indicadores para el país y Montevideo."""
    lineas = ["### Últimos valores", "", "| Indicador | Año | País | Montevideo |", "|---|---|---:|---:|"]
    for ind, nombre in ULTIMOS:
        f = obs[obs.indicador == ind]
        if f.empty:
            continue
        per = f.periodo.max()
        v = f[f.periodo == per].set_index("territorio_id").valor
        fmt = (lambda x: _num(x, 1)) if "tasa" in ind else _num
        mvd = fmt(v[mec.tid("departamento", "01")]) if mec.tid("departamento", "01") in v else "—"
        lineas.append(f"| {nombre} | {per} | {fmt(v[mec.PAIS]) if mec.PAIS in v else '—'} | {mvd} |")
    return lineas


def escribir_reporte(salida: Path, seccion: list[str]) -> None:
    path = salida / "reporte_validacion.md"
    if not path.exists():
        return
    bloque = "\n".join([MARCA, *seccion, FIN])
    texto = path.read_text(encoding="utf-8")
    if MARCA in texto and FIN in texto:
        texto = texto[:texto.index(MARCA)] + bloque + texto[texto.index(FIN) + len(FIN):]
    else:
        texto = texto.rstrip("\n") + "\n\n" + bloque + "\n"
    path.write_text(texto, encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path, help="carpeta mec_anuario de los originales (con capturas.json)")
    ap.add_argument("--salida", type=Path, default=Path("datos/salida"))
    ap.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes")
    ap.add_argument("--forzar", action="store_true", help="parsear de nuevo aunque las capturas no hayan cambiado")
    args = ap.parse_args(argv)
    args.salida.mkdir(parents=True, exist_ok=True)
    historial = Historial(args.salida)
    fuentes = cargar_fuentes(args.fuentes)
    try:
        r = cargar(args.entrada.parent, args.salida, fuentes, args.forzar, args.fuentes)
    except Exception as e:
        registro = leer_completo(args.entrada.parent, CARPETA)["capturas"]
        if registro:
            c = registro[-1]
            historial.agregar(nueva_captura(FUENTE_ID, c["archivo"], c["sha256"], ahora()), "error", f"{type(e).__name__}: {e}")
        raise
    for c in r.get("_capturas", []):
        if c["id"] in r.get("_parseadas", []):
            historial.agregar({**c, "fecha_proceso": ahora()}, r["resultado"], "")
    escribir_reporte(args.salida, seccion_reporte(r))
    print(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
