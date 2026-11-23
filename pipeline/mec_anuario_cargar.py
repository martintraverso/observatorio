"""F4.4 (#167): carga de los anuarios del MEC en las tablas del observatorio (AC-E4…E7, AC-E16).

Lee el registro de capturas (`<crudo>/mec_anuario/capturas.json`, de `mec_anuario_captura.py`) y, de cada anuario
vigente, los cuadros de la ola 1 con el mapeo por columna del registro de la fuente (`pipeline/mec_anuario.py`).
Escribe lo de la fuente en `<salida>/fuentes/mec_anuario_educacion/` y arma las tablas compartidas con
`comun.salida.combinar`, como la carga de ingresos (F3.4b):

- Cada año es una captura (AC-E4). Una captura ya cargada (mismo sha256) no se vuelve a parsear (AC-P8); una
  nueva reemplaza los valores de su año y el reporte dice cuántos cambiaron y el cambio más grande (AC-E6).
- Un año con error de descarga queda en el reporte y los demás se cargan igual (AC-E5).
- La serie nacional 2002–<año> sale del anuario más reciente; donde se superpone con un cuadro anual se guardan los
  dos y una diferencia es advertencia (AC-E7).
- Tasas derivadas (D2, AC-E16), con numerador y denominador del mismo cuadro, año, territorio y alcance:
  tasa de promoción = promovidos / (promovidos + no promovidos) × 100 en cada cuadro de rendimiento, y % de
  matrícula privada = privada / total × 100 en II-2.2.1. Cada una es un indicador propio con `es_derivado` y su
  `formula`. El % de asistencia insuficiente no se calcula: II-2.2.18 no trae la matrícula (pregunta en el PR).

Uso: python pipeline/mec_anuario_cargar.py datos/crudo/mec_anuario [--salida datos/salida] [--fuentes fuentes/] [--forzar]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import mec_anuario as mec
import pandas as pd
from ech_ingresos_captura import leer_completo, verificar
from ech_ingresos_cargar import _num, resumen_cambios
from mec_anuario_captura import CARPETA, FUENTE_ID

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

def leer_anuario(xlsx: bytes, anio: int, fuente: dict) -> tuple[pd.DataFrame, dict, list[str]]:
    """Valores de los cuadros de la ola 1 de un anuario, con sus pies y avisos por cuadro."""
    partes, pies, avisos = [], {}, []
    for cod, e in fuente["cuadros"].items():
        mapeo = (e.get("mapeo") or {}).get(anio)
        if e.get("ola") != 1 or not mapeo:
            continue
        c = mec.parsear_cuadro(xlsx, cod, anio, mapeo, e["tipos"][anio])
        partes.append(c.datos)
        pies[cod] = c.pie
        avisos += c.avisos + ([f"{cod} {anio}: {c.sin_dato} celdas sin dato («-», «s/d», vacías)"] if c.sin_dato else [])
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=mec.COLUMNAS), pies, avisos


def derivados(obs: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Tasas de D2 a partir de los conteos cargados (AC-E16): solo donde están numerador y denominador del mismo
    cuadro (el id lo dice), año, territorio y alcance. Devuelve las observaciones y {indicador: (fórmula, cuadro)}."""
    base = obs[~obs.indicador.str.contains(DERIVADO)]
    por = base.set_index(CLAVE).valor
    filas, formulas = [], {}

    def agregar(nuevo, num, valor_den, formula, ref):
        if valor_den:
            filas.append({**ref, "indicador": nuevo, "valor": float(num) / float(valor_den) * 100})
            formulas[nuevo] = (formula, ref["codigo_cuadro"])

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


def indicadores(obs: pd.DataFrame, fuente: dict, pies: dict, formulas: dict, serie: pd.DataFrame) -> pd.DataFrame:
    """El catálogo: nombre, unidad y columna de origen de cada indicador cargado; la nota es el pie del cuadro."""
    origen = {}
    for cod, e in fuente["cuadros"].items():
        for anio, m in sorted((e.get("mapeo") or {}).items()):
            for x in m or []:
                origen[x["id"]] = (cod, x.get("concepto", x["ruta"]), e)
    rutas_serie = dict(zip(serie.indicador, serie.ruta)) if len(serie) else {}
    filas = []
    for ind in sorted(obs.indicador.unique()):
        base, _, categoria = ind.partition("__")
        if ind in rutas_serie:
            filas.append({"codigo": ind, "nombre": f"Matrícula del sistema educativo: {rutas_serie[ind]}",
                          "unidad": "estudiantes", "columna_origen": f"Hoja {mec.SERIE} · {rutas_serie[ind]}",
                          "nota": "Serie del anuario más reciente.", "es_derivado": False, "formula": ""})
            continue
        if ind in formulas:
            formula, cod = formulas[ind]
            alcance = ind.split("_tasa_promocion")[-1].strip("_").replace("_", " ")
            nombre = (next((n for i, _, _, n in PCT_PRIVADA if i == ind), None)
                      or f"Tasa de promoción ({cod})" + (f": {alcance}" if alcance else ""))
            filas.append({"codigo": ind, "nombre": nombre, "unidad": "%", "columna_origen": f"Cuadro {cod} (calculado)",
                          "nota": "Calculado por el observatorio a partir de MEC.", "es_derivado": True,
                          "formula": formula})
            continue
        cod, concepto, e = origen.get(base) or origen.get(re.sub(r"__\d+$", "", base)) or (None, base, {})
        if cod is None:
            raise ErrorCarga(f"Indicador sin origen en el registro: {ind}")
        nombre = re.sub(r"\s*\(Todo el país.*", "", e["titulo"]).capitalize() + f": {concepto}"
        if categoria:
            nombre += f" — {categoria.replace('_', ' ')}"
        filas.append({"codigo": ind, "nombre": nombre, "unidad": e.get("unidad", "estudiantes"),
                      "columna_origen": f"Cuadro {cod} · {concepto}", "nota": " ".join(pies.get(cod, [])),
                      "es_derivado": False, "formula": ""})
    df = pd.DataFrame(filas)
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


def cargar(crudo: Path, salida: Path, fuentes: dict, forzar: bool = False) -> dict:
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
    if sin_cambios:  # AC-P8: nada nuevo, no se vuelve a parsear ni a publicar
        return {"resultado": "sin cambios", "capturas": len(registro), "vigentes": len(vigentes), "parseadas": 0,
                "_registro": registro, "_ultima": contenido.get("ultima_corrida") or {}}

    partes, pies, avisos, parseadas = [], {}, [], []
    for c in vigentes:
        anio = int(c["codigo"])
        datos, p, a = leer_anuario((crudo / c["archivo"]).read_bytes(), anio, fuente)
        partes.append(datos.assign(captura_id=c["id"]))
        pies.update(p)  # el pie del año más reciente queda como nota del indicador
        avisos += a
        parseadas.append(c["id"])
    ultimo = vigentes[-1]
    serie = mec.parsear_serie_matricula((crudo / ultimo["archivo"]).read_bytes()).assign(captura_id=ultimo["id"])
    obs = pd.concat([*partes, serie.drop(columns=["ruta"])], ignore_index=True)
    deriv, formulas = derivados(obs)
    obs = pd.concat([obs, deriv], ignore_index=True)
    if obs.duplicated(CLAVE).any():
        raise ErrorCarga("Valores repetidos para el mismo indicador, territorio y período: "
                         f"{obs[obs.duplicated(CLAVE, keep=False)][CLAVE].head(3).to_dict('records')}")
    nivel = obs.territorio_id.str.split("/").str[1]
    fuera = sorted(set(nivel) - set(fuente["niveles_publicados"]))
    if fuera:
        raise ErrorCarga(f"Observaciones en niveles que la fuente no publica: {fuera}")  # AC-P5
    ind = indicadores(obs, fuente, pies, formulas, serie)
    hoy = ahora()
    fecha_prev = {} if cap_prev is None else dict(zip(cap_prev.id, cap_prev.fecha_proceso))
    capturas = [nueva_captura(FUENTE_ID, c["archivo"], c["sha256"], hoy if c["id"] in parseadas else fecha_prev.get(c["id"], hoy),
                              url=c["url"], descargado=c["descargado"], vigente=c["vigente"]) for c in registro]
    cambios = resumen_cambios(obs_prev, obs[CLAVE + ["valor"]])
    publicar(salida, fuentes, obs.drop(columns=["codigo_cuadro", "celda"]).assign(es_estimado=False), capturas, ind)
    return {"resultado": "reprocesado" if forzar else "nuevo", "capturas": len(registro), "vigentes": len(vigentes),
            "parseadas": len(parseadas), "observaciones": len(obs), "derivadas": len(deriv), "cambios": cambios,
            "_registro": registro, "_ultima": contenido.get("ultima_corrida") or {}, "_obs": obs, "_avisos": avisos,
            "_solapes": solapes(obs), "_capturas": capturas}


# ---------------------------------------------------------------- reporte

def seccion_reporte(r: dict) -> list[str]:
    lineas = ["## Educación (MEC, Anuario Estadístico de Educación)", "",
              "| Año | Capturado | sha256 | Valores |", "|---|---|---|---:|"]
    obs = r.get("_obs")
    for c in (c for c in r["_registro"] if c["vigente"]):
        n = int((obs.captura_id == c["id"]).sum()) if obs is not None else "—"
        lineas.append(f"| {c['codigo']} | {c['descargado']} | `{c['sha256'][:12]}` | {n} |")
    errores = r["_ultima"].get("errores", [])
    lineas += ["", f"Última captura: {r['_ultima'].get('fecha', '—')}. "
               + ("Años con error (no se actualizaron; si ya tenían una captura, siguen sus valores):" if errores
                  else "Ningún año con error.")]
    lineas += [f"- **{e['codigo']}**: {e['error']} ({e['url']})" for e in errores]
    if r["resultado"] == "sin cambios":
        return lineas + ["", "Sin capturas nuevas: no se volvió a cargar."]
    cambios = r["cambios"]
    texto = f"{cambios['cambiaron']} valores cambiaron respecto de lo publicado"
    if cambios["mayor"]:
        m = cambios["mayor"]
        texto += f"; el cambio más grande: `{m['indicador']}`, {m['territorio_id']}, {m['periodo']}: {_num(m['antes'])} → {_num(m['ahora'])}"
    lineas += ["", f"Cambios: {texto}. Valores nuevos: {cambios['nuevos']}. Valores que ya no vienen: {cambios['quitados']}.",
               f"Tasas calculadas por el observatorio: {r['derivadas']}.", "",
               f"Serie nacional contra cuadros anuales (AC-E7): {len(r['_solapes'])} diferencias.",
               *[f"- {a}" for a in r["_solapes"]], "", f"Avisos de lectura: {len(r['_avisos'])}.",
               *[f"- {a}" for a in r["_avisos"]]]
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
        r = cargar(args.entrada.parent, args.salida, fuentes, args.forzar)
    except Exception as e:
        registro = leer_completo(args.entrada.parent, CARPETA)["capturas"]
        if registro:
            c = registro[-1]
            historial.agregar(nueva_captura(FUENTE_ID, c["archivo"], c["sha256"], ahora()), "error", f"{type(e).__name__}: {e}")
        raise
    for c in r.get("_capturas", []):
        if c["vigente"]:
            historial.agregar({**c, "fecha_proceso": ahora()}, r["resultado"], "")
    escribir_reporte(args.salida, seccion_reporte(r))
    print(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
