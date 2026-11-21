"""F3.4b (#138): carga de las series de ingresos (INE, ECH) en las tablas del observatorio.

Lee el registro de capturas de F3.4a (`<crudo>/ech_ingresos/capturas.json`), parsea con `parsear_serie` (F3.3)
cada captura vigente y le pone a cada valor su `captura_id`. Escribe lo de la fuente en
`<salida>/fuentes/ine_ech_ingresos_series/` y arma las tablas compartidas con `comun.salida.combinar`, como
`ech_cargar.py` (F2.5c):

- Una captura ya parseada (mismo id = mismo sha256) no se vuelve a parsear (AC-P8); con --forzar, sí.
- Solo las capturas vigentes dan observaciones: los valores de una captura nueva reemplazan a los anteriores del
  mismo indicador, territorio y período (AC-I6). Las anteriores quedan en `capturas` con vigente = false.
- La sección «Ingresos (ECH)» de reporte_validacion.md lista las planillas, las que dieron error en la última
  captura (AC-I5) y cuántos valores cambiaron respecto de lo publicado, con el cambio más grande (AC-I6).

Uso: python pipeline/ech_ingresos_cargar.py datos/crudo/ech_ingresos [--salida datos/salida] [--fuentes fuentes/] [--forzar]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from ech_ingresos import INDICADORES, parsear_serie
from ech_ingresos_captura import FUENTE_ID, leer_completo, verificar

from comun.capturas import Historial, ahora, nueva_captura
from comun.registro import RAIZ, cargar_fuentes
from comun.salida import carpeta_fuente, combinar, escribir_fuente

CLAVE = ["indicador", "territorio_id", "periodo"]
NOTA = ("Serie histórica de la Encuesta Continua de Hogares (INE). Desde 2025 el INE usa el ingreso disponible "
        "ajustado (YDA); la serie desde 2016 se recalculó con él. Los totales anuales son el promedio de los "
        "cuatro trimestres, como los publica el INE.")
MARCA, FIN = "<!-- ech_ingresos -->", "<!-- /ech_ingresos -->"


class ErrorCarga(ValueError):
    pass


def fuentes_registro() -> dict:
    return cargar_fuentes(RAIZ / "fuentes")


def indicadores() -> pd.DataFrame:
    return pd.DataFrame([{"codigo": i["indicador"], "nombre": i["nombre"], "unidad": i["unidad"], "tema": "Ingresos",
                          "columna_origen": f"Planilla {c}", "fuente_id": FUENTE_ID, "nota": NOTA}
                         for c, i in INDICADORES.items()])


def anteriores(salida: Path) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Lo último publicado de la fuente, según las tablas compartidas."""
    if not ((salida / "capturas.parquet").exists() and (salida / "observaciones.parquet").exists()):
        return None, None
    cap = pd.read_parquet(salida / "capturas.parquet")
    cap = cap[cap.fuente_id == FUENTE_ID]
    if cap.empty:
        return None, None
    obs = pd.read_parquet(salida / "observaciones.parquet")
    return obs[obs.captura_id.isin(cap.id)], cap


def resumen_cambios(antes: pd.DataFrame | None, ahora_: pd.DataFrame) -> dict:
    """Cuántos valores cambiaron respecto de lo publicado, cuántos son nuevos, cuántos ya no vienen (quitados) y el
    cambio más grande (AC-I6)."""
    if antes is None or antes.empty:
        return {"cambiaron": 0, "nuevos": len(ahora_), "quitados": 0, "mayor": None}
    quitados = len(antes[[*CLAVE]].merge(ahora_[[*CLAVE]], on=CLAVE, how="left", indicator=True).query("_merge == 'left_only'"))
    m = ahora_[[*CLAVE, "valor"]].merge(antes[[*CLAVE, "valor"]], on=CLAVE, how="left", suffixes=("", "_antes"))
    distintos = m[m.valor_antes.notna() & (m.valor != m.valor_antes)]
    mayor = None
    if not distintos.empty:
        f = distintos.loc[(distintos.valor - distintos.valor_antes).abs().idxmax()]
        mayor = {**{k: f[k] for k in CLAVE}, "antes": float(f.valor_antes), "ahora": float(f.valor)}
    return {"cambiaron": len(distintos), "nuevos": int(m.valor_antes.isna().sum()), "quitados": quitados, "mayor": mayor}


def publicar(salida: Path, fuentes: dict, obs, capturas) -> None:
    """Escribe la carpeta de la fuente y arma las tablas compartidas; si no encajan, deja la carpeta como estaba."""
    d = carpeta_fuente(salida, FUENTE_ID)
    antes = {p.name: p.read_bytes() for p in d.glob("*.parquet")} if d.exists() else {}
    escribir_fuente(salida, FUENTE_ID, obs, capturas, indicadores())
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


def cargar(crudo: Path, salida: Path, fuentes: dict, forzar: bool = False) -> dict:
    crudo, salida = Path(crudo), Path(salida)
    contenido = leer_completo(crudo)
    registro = contenido["capturas"]
    if not registro:
        raise ErrorCarga(f"No hay capturas en {crudo / 'ech_ingresos' / 'capturas.json'}")
    for c in registro:
        verificar(crudo, c)
    obs_prev, cap_prev = anteriores(salida)
    ya = set() if forzar or obs_prev is None else set(obs_prev.captura_id)
    fecha_prev = {} if cap_prev is None else dict(zip(cap_prev.id, cap_prev.fecha_proceso))

    vigentes = [c for c in registro if c["vigente"]]
    if not vigentes:
        raise ErrorCarga("No hay capturas vigentes")
    partes, parseadas, llamadas = [], [], {}
    for c in vigentes:
        if c["id"] in ya:
            partes.append(obs_prev[obs_prev.captura_id == c["id"]])
            continue
        df = parsear_serie((crudo / c["archivo"]).read_bytes(), c["codigo"])
        llamadas[c["codigo"]] = df.attrs.get("llamadas", {})
        partes.append(df.drop(columns=["unidad", "codigo_planilla"]).assign(captura_id=c["id"]))
        parseadas.append(c["id"])
    obs = pd.concat(partes, ignore_index=True)
    if obs.duplicated(CLAVE).any():
        raise ErrorCarga(f"Valores repetidos para el mismo indicador, territorio y período: "
                         f"{obs[obs.duplicated(CLAVE, keep=False)][CLAVE].head(3).to_dict('records')}")
    nivel = obs.territorio_id.str.split("/").str[1]
    fuera = sorted(set(nivel) - set(fuentes[FUENTE_ID]["niveles_publicados"]))
    if fuera:
        raise ErrorCarga(f"Observaciones en niveles que la fuente no publica: {fuera}")  # AC-P5

    hoy = ahora()
    capturas = [nueva_captura(FUENTE_ID, c["archivo"], c["sha256"], hoy if c["id"] in parseadas
                              else fecha_prev.get(c["id"], hoy), url=c["url"], descargado=c["descargado"],
                              vigente=c["vigente"]) for c in registro]
    cambios = resumen_cambios(obs_prev, obs)
    sin_cambios = (not parseadas and cap_prev is not None
                   and sorted(zip(cap_prev.id, cap_prev.vigente)) == sorted((c["id"], c["vigente"]) for c in registro))
    if not sin_cambios:
        publicar(salida, fuentes, obs, capturas)
    return {"resultado": "sin cambios" if sin_cambios else ("reprocesado" if forzar else "nuevo"),
            "capturas": len(registro), "vigentes": len(vigentes), "parseadas": len(parseadas),
            "observaciones": len(obs), "errores_captura": len(contenido.get("ultima_corrida", {}).get("errores", [])),
            "cambios": cambios, "_registro": registro, "_ultima": contenido.get("ultima_corrida") or {}, "_obs": obs,
            "_capturas": capturas, "_parseadas": parseadas}


def _num(v: float, decimales: int = 0) -> str:
    return f"{v:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def seccion_reporte(registro: list[dict], ultima: dict, obs: pd.DataFrame, cambios: dict) -> list[str]:
    lineas = ["## Ingresos (ECH)", "", "| Planilla | Indicador | Capturada | sha256 | Períodos |", "|---|---|---|---|---|"]
    for c in (c for c in registro if c["vigente"]):
        ind = INDICADORES[c["codigo"]]["indicador"]
        per = obs[obs.indicador == ind].drop_duplicates("periodo")
        rango = f"{per.periodo_inicio.min()} a {per.periodo_fin.max()}" if len(per) else "—"
        lineas.append(f"| {c['codigo']} | `{ind}` | {c['descargado']} | `{c['sha256'][:12]}` | {len(per)} ({rango}) |")
    errores = ultima.get("errores", [])
    lineas += ["", f"Última captura: {ultima.get('fecha', '—')}. "
               + ("Planillas con error (no se actualizaron; si ya tenían una captura, siguen sus valores anteriores):" if errores else "Ninguna planilla con error.")]
    lineas += [f"- **{e['codigo']}**: {e['error']} ({e['url']})" for e in errores]
    if ultima.get("revertidas"):
        lineas += ["", "Volvieron a una versión ya capturada (el INE retiró una revisión): "
                   + ", ".join(ultima["revertidas"]) + "."]
    lineas += ["", "Las medianas y el ingreso de los ocupados no se capturan: sus enlaces del INE dan 404 "
               "(`enlaces_rotos` en el registro de la fuente)."]
    n = cambios["cambiaron"]
    texto = f"{n} valor{'es' if n != 1 else ''} {'cambiaron' if n != 1 else 'cambió'} respecto de lo publicado"
    if cambios["mayor"]:
        m = cambios["mayor"]
        dif = m["ahora"] - m["antes"]
        d = 0 if abs(dif) >= 1 else 4  # una revisión de decimales no se ve redondeada a pesos
        texto += (f"; el cambio más grande: `{m['indicador']}`, {m['territorio_id']}, {m['periodo']}: "
                  f"{_num(m['antes'], d)} → {_num(m['ahora'], d)} ({'+' if dif >= 0 else '−'}{_num(abs(dif), d)})")
    lineas += ["", f"Cambios: {texto}. Valores nuevos: {cambios['nuevos']}. Valores que ya no vienen: {cambios['quitados']}."]
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
    ap.add_argument("entrada", type=Path, help="carpeta ech_ingresos de los originales (con capturas.json)")
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
        registro = leer_completo(args.entrada.parent)["capturas"]
        if registro:
            c = registro[-1]
            historial.agregar(nueva_captura(FUENTE_ID, c["archivo"], c["sha256"], ahora()), "error",
                              f"{type(e).__name__}: {e}")
        raise
    registro, ultima, obs = r.pop("_registro"), r.pop("_ultima"), r.pop("_obs")
    capturas = {c["id"]: c for c in r.pop("_capturas")}
    parseadas = r.pop("_parseadas")
    for i in parseadas or [[c for c in capturas.values() if c["vigente"]][-1]["id"]]:
        historial.agregar({**capturas[i], "fecha_proceso": ahora()}, r["resultado"],
                          "" if parseadas else "ninguna captura nueva")
    escribir_reporte(args.salida, seccion_reporte(registro, ultima, obs, r["cambios"]))
    print(json.dumps(r, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
