"""F2.5c: carga de los informes de mercado de trabajo (INE, ECH) en las tablas del observatorio.

Lee el registro de capturas de F2.5b (`<crudo>/ech_mt/capturas.json`), parsea con `parsear_informe` (F2.4) cada
captura vigente y le pone a cada valor su `captura_id`. Escribe lo de la fuente en
`<salida>/fuentes/ine_ech_mercado_trabajo_departamental/` y arma las tablas compartidas con
`comun.salida.combinar`, junto con las del Censo.

- Una captura que ya se parseó (mismo id = mismo sha256) no se vuelve a parsear: se reutilizan sus
  observaciones (AC-L4, AC-P8). Con --forzar se parsea todo de nuevo.
- Solo las capturas vigentes dan observaciones; las anteriores quedan en `capturas` (vigente = false), trazables.
- Cada valor queda en el nivel en que lo publica el INE (SYSTEM.md §4, AC-P5): país solo si el informe trae
  «Total país», departamentos y municipios de Montevideo.

Uso: python pipeline/ech_cargar.py datos/crudo/ech_mt [--salida datos/salida] [--fuentes fuentes/] [--forzar]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from ech_captura import FUENTE_ID, leer_registro, verificar
from ech_mercado_trabajo import INDICADORES, parsear_informe

from comun.capturas import Historial, ahora, nueva_captura
from comun.registro import RAIZ, cargar_fuentes
from comun.salida import carpeta_fuente, combinar, escribir_fuente

NOMBRES = {
    "tasa_actividad": ("Tasa de actividad", "Cuadros 1 y 4: Actividad"),
    "tasa_empleo": ("Tasa de empleo", "Cuadros 1 y 4: Empleo"),
    "tasa_desempleo": ("Tasa de desempleo", "Cuadros 1 y 4: Desempleo"),
    "activos": ("Activos", "Cuadros 2 y 5: Activos"),
    "ocupados": ("Ocupados", "Cuadros 2 y 5: Empleados"),
    "desocupados": ("Desocupados", "Cuadros 2 y 5: Desempleados"),
    "tasa_no_registro": ("No registro a la seguridad social", "Cuadros 3 y 6: No registro (en %)"),
}
NOTA = ("Estimación de la Encuesta Continua de Hogares para un trimestre móvil, por lugar de residencia. "
        "Ver las advertencias del INE en la ficha de la fuente.")


class ErrorCarga(ValueError):
    pass


def indicadores() -> pd.DataFrame:
    return pd.DataFrame([{"codigo": c, "nombre": NOMBRES[c][0], "unidad": u, "tema": "Trabajo",
                          "columna_origen": NOMBRES[c][1], "fuente_id": FUENTE_ID, "nota": NOTA}
                         for c, u in INDICADORES.items()])


def anteriores(salida: Path) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Lo último publicado de la fuente, según las tablas compartidas (no la carpeta de la fuente: en Actions no
    existe, y una corrida que falló pudo dejarla escrita sin publicar)."""
    if not ((salida / "capturas.parquet").exists() and (salida / "observaciones.parquet").exists()):
        return None, None
    cap = pd.read_parquet(salida / "capturas.parquet")
    cap = cap[cap.fuente_id == FUENTE_ID]
    if cap.empty:
        return None, None
    obs = pd.read_parquet(salida / "observaciones.parquet")
    return obs[obs.captura_id.isin(cap.id)], cap


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
    registro = leer_registro(crudo)
    if not registro:
        raise ErrorCarga(f"No hay capturas en {Path(crudo) / 'ech_mt' / 'capturas.json'}")
    for c in registro:
        verificar(crudo, c)
    obs_prev, cap_prev = anteriores(salida)
    # solo se reutilizan capturas que ya dieron observaciones (una que vuelve a ser vigente se parsea)
    ya = set() if forzar or obs_prev is None else set(obs_prev.captura_id)
    fecha_prev = {} if cap_prev is None else dict(zip(cap_prev.id, cap_prev.fecha_proceso))

    vigentes = [c for c in registro if c["vigente"]]
    if not vigentes:
        raise ErrorCarga("No hay capturas vigentes")
    partes, parseadas, advertencias = [], [], {}
    for c in vigentes:
        if c["id"] in ya:
            partes.append(obs_prev[obs_prev.captura_id == c["id"]])
            continue
        df = parsear_informe((Path(crudo) / c["archivo"]).read_text(encoding="utf-8"), archivo=Path(c["archivo"]).name)
        if set(df.periodo) != {c["periodo"]}:
            raise ErrorCarga(f"{c['archivo']}: el informe es de {sorted(set(df.periodo))} y la captura dice {c['periodo']}")
        partes.append(df.assign(captura_id=c["id"]))
        parseadas.append(c)
        advertencias[c["id"]] = df.attrs.get("advertencias", [])
    obs = pd.concat(partes, ignore_index=True)

    nivel = obs.territorio_id.str.split("/").str[1]
    fuera = sorted(set(nivel) - set(fuentes[FUENTE_ID]["niveles_publicados"]))
    if fuera:
        raise ErrorCarga(f"Observaciones en niveles que la fuente no publica: {fuera}")  # AC-P5

    hoy = ahora()
    capturas = [nueva_captura(FUENTE_ID, c["archivo"], c["sha256"], fecha_prev.get(c["id"], hoy) if c not in parseadas
                              else hoy, url=c["url"], descargado=c["descargado"], vigente=c["vigente"])
                for c in registro]
    sin_cambios = (not parseadas and cap_prev is not None
                   and sorted(zip(cap_prev.id, cap_prev.vigente)) == sorted((c["id"], c["vigente"]) for c in registro))
    if not sin_cambios:
        publicar(salida, fuentes, obs, capturas)
    return {"resultado": "sin cambios" if sin_cambios else ("reprocesado" if forzar else "nuevo"),
            "capturas": len(registro), "vigentes": sum(c["vigente"] for c in registro),
            "parseadas": len(parseadas), "reutilizadas": sum(c["vigente"] for c in registro) - len(parseadas),
            "observaciones": len(obs), "advertencias": sum(map(len, advertencias.values())),
            "_capturas": capturas, "_parseadas": [c["id"] for c in parseadas], "_advertencias": advertencias}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path, help="carpeta ech_mt de los originales (con capturas.json)")
    ap.add_argument("--salida", type=Path, default=Path("datos/salida"))
    ap.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes")
    ap.add_argument("--forzar", action="store_true", help="parsear de nuevo aunque las capturas no hayan cambiado")
    args = ap.parse_args(argv)
    args.salida.mkdir(parents=True, exist_ok=True)
    historial = Historial(args.salida)
    try:
        r = cargar(args.entrada.parent, args.salida, cargar_fuentes(args.fuentes), args.forzar)
    except Exception as e:
        registro = leer_registro(args.entrada.parent)
        if registro:
            c = registro[-1]
            historial.agregar(nueva_captura(FUENTE_ID, c["archivo"], c["sha256"], ahora()), "error",
                              f"{type(e).__name__}: {e}")
        raise
    capturas = {c["id"]: c for c in r.pop("_capturas")}
    parseadas, advertencias = r.pop("_parseadas"), r.pop("_advertencias")
    if parseadas:
        for i in parseadas:
            texto = "; ".join(advertencias.get(i, []))
            historial.agregar(capturas[i], r["resultado"], f"{PREFIJO_ADVERTENCIA}{texto}" if texto else "")
    else:
        ultima = {**[c for c in capturas.values() if c["vigente"]][-1], "fecha_proceso": ahora()}
        historial.agregar(ultima, r["resultado"], "ninguna captura nueva" if r["resultado"] == "sin cambios" else "")
    escribir_reporte(args.salida, capturas)
    print(json.dumps(r, ensure_ascii=False))
    return 0


PREFIJO_ADVERTENCIA = "advertencias: "
MARCA, FIN = "<!-- ech_mt -->", "<!-- /ech_mt -->"


def escribir_reporte(salida: Path, capturas: dict) -> None:
    """Sección de la ECH en reporte_validacion.md: las advertencias de las capturas vigentes, tomadas del
    historial (que se publica), así no se pierden cuando no se vuelve a parsear. F2.6 suma los controles."""
    path = salida / "reporte_validacion.md"
    if not path.exists():
        return
    h = Historial(salida).leer()
    h = h[(h.fuente_id == FUENTE_ID) & h.detalle.fillna("").str.startswith(PREFIJO_ADVERTENCIA)]
    vigentes = {i: c for i, c in capturas.items() if c["vigente"]}
    filas = [(r.archivo, r.detalle.removeprefix(PREFIJO_ADVERTENCIA)) for r in h.drop_duplicates("id", keep="last")
             .itertuples() if r.id in vigentes]
    lineas = [MARCA, "## Mercado de trabajo (ECH): advertencias", "",
              f"Capturas vigentes: {len(vigentes)}. Diferencias de redondeo aceptadas (hasta 0,1): {len(filas)}.", ""]
    lineas += [f"- `{Path(a).name}`: {d}" for a, d in sorted(filas)] or ["- Ninguna."]
    seccion = "\n".join([*lineas, FIN])
    texto = path.read_text(encoding="utf-8")
    if MARCA in texto and FIN in texto:
        texto = texto[:texto.index(MARCA)] + seccion + texto[texto.index(FIN) + len(FIN):]
    else:
        texto = texto.rstrip("\n") + "\n\n" + seccion + "\n"
    path.write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
