"""F3.3 (#127): parser de las «Series históricas ECH Ingresos de las personas y los hogares» (INE).

`parsear_serie(xlsx_bytes, codigo)` es una función pura: recibe una planilla (ECHING07…14, ECHINGRESOS2/3) y
devuelve una fila por territorio y período, sin red ni disco. La captura (descarga, sha256, captura_id) y la carga
son de F3.4. Formato de las planillas: fuentes/ine_ech_ingresos_series.yml.

- Columnas -> territorios (AC-I7): Total País -> pais/UY; Montevideo -> departamento/01; Interior · Total,
  · Localidades de 5.000 o más hab., · Localidades Pequeñas y Zonas rurales -> region/... Una columna
  desconocida hace fallar la planilla.
- Filas -> períodos (AC-I8): «Enero - Marzo/16» -> trimestre 2016-T1; «Total 2016» -> anio 2016. Las filas con
  el año y las notas al pie no son datos. Las llamadas («(1)») se sacan de la etiqueta y su texto queda en
  `df.attrs["llamadas"]`; todas las notas al pie, en `df.attrs["notas_al_pie"]`.
- Indicador por planilla (AC-I9), distinto por medida, variante y base de precios; el título de la planilla
  tiene que corresponder al código.
- Valores con la precisión publicada (AC-I10). Decisiones del mantenedor (PR #134, 2026-11-20): unidades «por
  mes»; los totales anuales se guardan aunque la planilla los calcule como promedio de los trimestres (se usa el
  valor calculado guardado en la planilla); los valores de 2026, redondeados en la planilla, se guardan tal cual.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd
from territorios_2023 import tid

from comun.periodos import anio, trimestre
from comun.xlsx import leer_primera_hoja


class ErrorSerie(ValueError):
    """La planilla no tiene el formato conocido: no se carga nada de ella."""


CORRIENTES = "pesos corrientes por mes"
ENE2005 = "pesos de enero de 2005 por mes"
HOGAR = "Ingreso medio de los hogares"
PC = "Ingreso medio per cápita de los hogares"
VARIANTES = {  # sufijo -> (aguinaldo, valor locativo)
    "cagu_cvl": ("con aguinaldo", "con valor locativo"), "sagu_cvl": ("sin aguinaldo", "con valor locativo"),
    "cagu_svl": ("con aguinaldo", "sin valor locativo"), "sagu_svl": ("sin aguinaldo", "sin valor locativo"),
}


def _indicador(codigo: str, medida: str, variante: str, base: str) -> dict:
    agu, vl = VARIANTES[variante]
    prefijo = "ing_hogar_medio" if medida == HOGAR else "ing_pc_medio"
    sufijo = "_ene2005" if base == ENE2005 else ""
    precios = "a precios corrientes" if base == CORRIENTES else "a precios de enero de 2005"
    return {"indicador": f"{prefijo}_{variante}{sufijo}", "nombre": f"{medida} ({agu}, {vl}, {precios})",
            "unidad": base, "titulo": ["hogares" if medida == HOGAR else "per capita", agu, vl,
                                       "precios corrientes" if base == CORRIENTES else "precios de enero 2005"]}


# Planilla -> indicador (AC-I9; mismo mapeo que `archivos` en el registro).
INDICADORES = {
    **{f"ECHING{7 + i:02d}": _indicador(f"ECHING{7 + i:02d}", HOGAR, v, CORRIENTES) for i, v in enumerate(VARIANTES)},
    **{f"ECHING{11 + i}": _indicador(f"ECHING{11 + i}", PC, v, CORRIENTES) for i, v in enumerate(VARIANTES)},
    "ECHINGRESOS2": _indicador("ECHINGRESOS2", HOGAR, "sagu_svl", ENE2005),
    "ECHINGRESOS3": _indicador("ECHINGRESOS3", PC, "sagu_svl", ENE2005),
}

INTERIOR = "interior"
# Encabezado (las dos filas juntas, plegado) -> territorio. «Total» solo vale bajo el grupo «Interior».
COLUMNAS = {
    "total pais": tid("pais", "UY"),
    "montevideo": tid("departamento", "01"),
    "total": tid("region", INTERIOR),
    "localidades de 5.000 o mas hab.": tid("region", "interior-5000"),
    "localidades pequenas y zonas rurales": tid("region", "interior-menores"),
}
TRIMESTRES = {"enero - marzo": 1, "abril - junio": 2, "julio - setiembre": 3, "octubre - diciembre": 4}
LLAMADAS = r"((?:\s*\(\d+\))*)"
FILA_TRIMESTRE = re.compile(rf"^({'|'.join(TRIMESTRES)})/(\d{{2}}){LLAMADAS}$")
FILA_TOTAL = re.compile(rf"^total (\d{{4}}){LLAMADAS}$")
NOTA = re.compile(r"^\((\d+)\):\s*(.+)$")


def plegar(texto) -> str:
    """Minúsculas, sin tildes y con espacios simples: 'Total País ' -> 'total pais'."""
    t = "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def _encabezado(filas: dict) -> tuple[int, dict[int, str]]:
    """Fila del encabezado y columna -> territorio (AC-I7)."""
    fila = next((r for r in sorted(filas) if plegar(filas[r].get(1, "")).startswith("mes, trimestre y ano")), None)
    if fila is None:
        raise ErrorSerie("No encuentro el encabezado «Mes, Trimestre y Año»")
    grupo = {plegar(v) for v in filas.get(fila - 1, {}).values()}
    columnas = {}
    for c in sorted((set(filas[fila]) | set(filas.get(fila + 1, {}))) - {1}):
        rotulo = plegar(f"{filas[fila].get(c, '')} {filas.get(fila + 1, {}).get(c, '')}")
        if rotulo not in COLUMNAS or (rotulo == "total" and "interior" not in grupo):
            raise ErrorSerie(f"Columna desconocida en el encabezado: {rotulo!r}")
        columnas[c] = COLUMNAS[rotulo]
    if sorted(columnas.values()) != sorted(COLUMNAS.values()):
        raise ErrorSerie(f"Faltan columnas en el encabezado: {sorted(set(COLUMNAS.values()) - set(columnas.values()))}")
    return fila, columnas


def _llamadas(texto: str) -> list[str]:
    return re.findall(r"\((\d+)\)", texto or "")


def parsear_serie(xlsx: bytes, codigo: str) -> pd.DataFrame:
    """Una fila por territorio y período (AC-I7…I10).

    Columnas: territorio_id, indicador, valor, unidad, es_estimado, codigo_planilla y las del período (periodo,
    periodo_inicio, periodo_fin, tipo_periodo). En `attrs`: titulo, llamadas {periodo: [textos]} y notas_al_pie.
    """
    if codigo not in INDICADORES:
        raise ErrorSerie(f"Código de planilla desconocido: {codigo!r} (conocidos: {', '.join(INDICADORES)})")
    ind = INDICADORES[codigo]
    try:
        filas = leer_primera_hoja(xlsx)
    except (ValueError, KeyError, OSError, ET.ParseError, zipfile.BadZipFile) as e:
        raise ErrorSerie(f"{codigo}: no se puede leer la planilla: {e}") from e

    fila_enc, columnas = _encabezado(filas)
    titulo = " ".join(str(filas[r][1]).strip() for r in sorted(filas) if r < fila_enc - 1 and 1 in filas[r]
                      and isinstance(filas[r][1], str))
    faltan = [frase for frase in ind["titulo"] if frase not in plegar(titulo)]
    if faltan:
        raise ErrorSerie(f"{codigo}: el título no corresponde a {ind['indicador']} (falta {faltan}): {titulo!r}")

    datos, pie, vistos = [], [], set()
    en_pie, bloque = False, None  # bloque: el año de la última fila con el año
    for r in sorted(f for f in filas if f > fila_enc + 1):
        celdas = filas[r]
        rotulo = celdas.get(1)
        valores = {c: v for c, v in celdas.items() if c != 1}
        if isinstance(rotulo, str) and plegar(rotulo).startswith("fuente:"):
            en_pie = True
        if en_pie:
            if any(isinstance(v, float) for v in celdas.values()):
                raise ErrorSerie(f"{codigo}: fila {r} del pie (después de «Fuente:») con números: {celdas}")
            pie += [str(v).strip() for _, v in sorted(celdas.items()) if str(v).strip()]
            continue
        if isinstance(rotulo, float) and not valores:  # fila con el año, separa los bloques
            bloque = int(rotulo)
            continue
        if rotulo is None and not valores:
            continue
        texto = plegar(rotulo) if isinstance(rotulo, str) else ""
        if m := FILA_TRIMESTRE.match(texto):
            periodo = trimestre(2000 + int(m.group(2)), TRIMESTRES[m.group(1)])
        elif m := FILA_TOTAL.match(texto):
            periodo = anio(int(m.group(1)))
        else:
            raise ErrorSerie(f"{codigo}: fila {r} desconocida: {rotulo!r} {valores}")
        if bloque is not None and periodo.inicio.year != bloque:  # «Julio - Setiembre/61» en el bloque 2016
            raise ErrorSerie(f"{codigo}: fila {r} ({rotulo!r}): el año no coincide con el del bloque ({bloque})")
        if periodo.etiqueta in vistos:
            raise ErrorSerie(f"{codigo}: el período {periodo.etiqueta} aparece dos veces")
        vistos.add(periodo.etiqueta)
        sobran = set(valores) - set(columnas)
        if sobran:
            raise ErrorSerie(f"{codigo}: fila {r} con valores fuera de las columnas conocidas: {sorted(sobran)}")
        for c, territorio in columnas.items():
            v = valores.get(c)
            if not isinstance(v, float):
                raise ErrorSerie(f"{codigo}: {periodo.etiqueta}, {territorio}: falta el valor o no es un número ({v!r})")
            datos.append({"territorio_id": territorio, "indicador": ind["indicador"], "valor": v, "unidad": ind["unidad"],
                          "es_estimado": False, "codigo_planilla": codigo, "_llamadas": _llamadas(rotulo),
                          **periodo.columnas()})
    if not datos:
        raise ErrorSerie(f"{codigo}: la planilla no tiene datos")

    notas = {n: t.strip() for linea in pie if (m := NOTA.match(linea)) for n, t in [m.groups()]}
    llamadas = {}
    for d in datos:
        for n in d.pop("_llamadas"):
            if n not in notas:
                raise ErrorSerie(f"{codigo}: {d['periodo']} tiene la llamada ({n}) y no hay nota al pie con ese número")
            llamadas.setdefault(d["periodo"], [])
            if notas[n] not in llamadas[d["periodo"]]:
                llamadas[d["periodo"]].append(notas[n])
    df = pd.DataFrame(datos)
    df.attrs.update({"titulo": titulo, "llamadas": llamadas, "notas_al_pie": pie})
    return df
