"""F2.4: parser del informe «Mercado de trabajo por área geográfica de residencia» (INE, ECH).

`parsear_informe(html)` es una función pura: recibe el HTML de un informe mensual y devuelve una fila por
territorio e indicador, sin red ni disco. La captura (descarga, sha256, captura_id) y la carga son de F2.5.

Cada informe trae 6 cuadros (ver fuentes/ine_ech_mercado_trabajo_departamental.yml):
  1-3: tasas, miles de personas y no registro por departamento (y «Total país» en los informes recientes)
  4-6: lo mismo por municipio de Montevideo (y «Total Montevideo», que repite el departamento 01)

Los formatos conocidos (encabezados por época, columna PET, filas de total, coma o punto decimal) se
aceptan de forma explícita; cualquier otro hace fallar el informe (AC-L9). No se descarta ninguna fila en
silencio (AC-L7) y se guarda cada valor en el nivel en que el INE lo publica (SYSTEM.md §4).
"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

import pandas as pd
from territorios_2023 import NOMBRES_DEPTO, tid

from comun.periodos import Periodo, trimestre_movil

# indicador -> unidad (AC-L5). Los miles se guardan como los publica el INE.
INDICADORES = {
    "tasa_actividad": "%", "tasa_empleo": "%", "tasa_desempleo": "%",
    "activos": "miles de personas", "ocupados": "miles de personas", "desocupados": "miles de personas",
    "tasa_no_registro": "%",
}

# Encabezados conocidos de cada columna -> indicador (None = columna que no se guarda).
COLUMNAS = {
    "tasa de actividad": "tasa_actividad", "actividad": "tasa_actividad",
    "tasa de empleo": "tasa_empleo", "empleo": "tasa_empleo",
    "tasa de desempleo": "tasa_desempleo", "desempleo": "tasa_desempleo",
    "total de activos": "activos", "activos": "activos",
    "total de empleados": "ocupados", "empleados": "ocupados",
    "total de desempleados": "desocupados", "desempleados": "desocupados",
    "no registro (en %)": "tasa_no_registro",
}
# Columnas que el INE publica y no son indicadores de F2: solo se aceptan en su cuadro.
IGNORADAS = {"pet (en miles)": 5}  # población en edad de trabajar, cuadro 5 en 2022 y 2024

# Los 6 cuadros, en orden: primera columna e indicadores que tiene que traer cada uno.
CUADROS = [
    ("departamento", ["tasa_actividad", "tasa_empleo", "tasa_desempleo"]),
    ("departamento", ["activos", "ocupados", "desocupados"]),
    ("departamento", ["tasa_no_registro"]),
    ("municipio", ["tasa_actividad", "tasa_empleo", "tasa_desempleo"]),
    ("municipio", ["activos", "ocupados", "desocupados"]),
    ("municipio", ["tasa_no_registro"]),
]
MUNICIPIOS = ["A", "B", "C", "CH", "D", "E", "F", "G"]
TOTAL_PAIS, TOTAL_MVD = "total pais", "total montevideo"

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "setiembre": 9, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


def mes(palabra: str) -> int | None:
    """'setiembre', 'set', 'sept' o 'agos' -> número de mes: el nombre o un prefijo de 3 letras o más."""
    if len(palabra) < 3:
        return None
    numeros = {n for nombre, n in MESES.items() if nombre.startswith(palabra)}
    return numeros.pop() if len(numeros) == 1 else None


class ErrorInforme(ValueError):
    """El informe no tiene un formato conocido: la corrida falla en vez de guardar datos dudosos."""


# ---------------------------------------------------------------- utilidades

def plegar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios simples: '  TREINTA  y Tres ' -> 'treinta y tres'."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c))
    return " ".join(sin_tildes.lower().split())


DEPARTAMENTOS = {plegar(nombre): codigo for codigo, nombre in NOMBRES_DEPTO.items()}


def codigo_departamento(nombre: str) -> str:
    """Nombre de departamento del informe -> código INE (AC-L6)."""
    try:
        return DEPARTAMENTOS[plegar(nombre)]
    except KeyError:
        raise ErrorInforme(f"Departamento desconocido: {nombre!r}") from None


NUMERO = re.compile(r"^\d+(?:[.,]\d+)?$")


def numero(texto: str) -> float:
    """'7,1' -> 7.1 y '14.2' -> 14.2 (AC-L7). Un solo separador decimal; nada de miles ni textos."""
    t = texto.strip()
    if not NUMERO.match(t):
        raise ErrorInforme(f"Número inválido: {texto!r}")
    return float(t.replace(",", "."))


class _Html(HTMLParser):
    """Las tablas del HTML (filas de celdas) y su texto visible, sin <script> ni <style>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tablas, self.fila, self.celda, self.texto, self.oculto = [], None, None, [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.oculto += 1
        elif tag == "table":
            self.tablas.append([])
        elif tag == "tr" and self.tablas:
            self.fila = []
        elif tag in ("td", "th") and self.fila is not None:
            self.celda = []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.oculto = max(0, self.oculto - 1)
        elif tag in ("td", "th") and self.celda is not None:
            self.fila.append(" ".join(" ".join(self.celda).split()))
            self.celda = None
        elif tag == "tr" and self.fila is not None:
            self.tablas[-1].append(self.fila)
            self.fila = None

    def handle_data(self, data):
        if self.oculto:
            return
        self.texto.append(data)
        if self.celda is not None:
            self.celda.append(data)


def leer_html(html: str) -> tuple[list[list[list[str]]], str]:
    """(tablas, texto visible plegado)."""
    p = _Html()
    p.feed(html)
    return p.tablas, plegar(" ".join(p.texto))


# ---------------------------------------------------------------- período (AC-L10)

def _fin_del_rango(texto: str) -> tuple[int, int] | None:
    """(año, mes final) de un texto con meses y años, o None si no trae ninguno.

    Formatos aceptados (y nada más): «mes año» (mes final, como «Febrero 2022») y «mes [año] mes [año]»
    (trimestre: el primer mes tiene que ser el final menos 2, y los años, coherentes con el cruce de año).
    """
    fichas = []
    for palabra in re.findall(r"[a-z]+|\d+", texto):
        if m := mes(palabra):
            fichas.append(("m", m))
        elif re.fullmatch(r"(19|20)\d\d", palabra):
            fichas.append(("a", int(palabra)))
    forma = "".join(f for f, _ in fichas)
    v = [x for _, x in fichas]
    if not fichas:
        return None
    if forma == "ma":
        return v[1], v[0]
    rangos = {  # forma -> (mes inicial, año inicial, mes final, año final)
        "mma": lambda: (v[0], None, v[1], v[2]),             # Julio - Setiembre 2024
        "mama": lambda: (v[0], v[1], v[2], v[3]),            # Noviembre 2023 - Enero 2024
        "mam": lambda: (v[0], v[1], v[2], v[1] + (v[2] < v[0])),  # Diciembre 2024 - Febrero
    }
    if forma in rangos:
        m1, a1, m2, a2 = rangos[forma]()
        if (m2 - m1) % 12 != 2:
            raise ErrorInforme(f"Período desconocido: {texto!r} (el trimestre tiene que ser de 3 meses)")
        if a1 is not None and a2 != a1 + (m2 < m1):
            raise ErrorInforme(f"Período desconocido: {texto!r} (años incoherentes)")
        return a2, m2
    raise ErrorInforme(f"Período desconocido: {texto!r}")


CODIGO_DOCUMENTO = re.compile(r"in[ _]soc[ _]mtr[ _](\d{4})[ _]m[ _](\d{2})")


def _periodo_titulo(texto: str) -> tuple[int, int] | None:
    """(año, mes final) del encabezado: entre «Actividad, Empleo y Desempleo» y «Introducción»."""
    m = re.search(r"actividad, empleo y desempleo(.*?)introduccion", texto)
    if not m:
        return None
    titulo = m.group(1)
    candidatos = set()
    if c := CODIGO_DOCUMENTO.search(titulo):
        candidatos.add((int(c.group(1)), int(c.group(2))))
        titulo = CODIGO_DOCUMENTO.sub(" ", titulo)
    if fin := _fin_del_rango(titulo):
        candidatos.add(fin)
    if len(candidatos) > 1:
        raise ErrorInforme(f"El encabezado trae períodos distintos: {sorted(candidatos)}")
    return candidatos.pop() if candidatos else None


def _periodo_archivo(nombre: str) -> tuple[int, int] | None:
    n = plegar(nombre).replace("_", " ").replace("-", " ")
    if c := CODIGO_DOCUMENTO.search(n):
        return int(c.group(1)), int(c.group(2))
    return _fin_del_rango(n)


def periodo_de_nombre(nombre: str) -> Periodo | None:
    """Trimestre móvil a partir de un nombre de archivo o de publicación, o None si no trae período."""
    fin = _periodo_archivo(nombre)
    if fin and not 1 <= fin[1] <= 12:
        raise ErrorInforme(f"Período desconocido: mes {fin[1]}")
    return trimestre_movil(*fin) if fin else None


def periodo_del_informe(html: str, archivo: str | None = None, texto: str | None = None) -> Periodo:
    """Trimestre móvil del informe: del encabezado y, si no lo trae, del nombre del archivo.
    Si los dos lo traen, tienen que coincidir."""
    del_titulo = _periodo_titulo(texto if texto is not None else leer_html(html)[1])
    del_archivo = _periodo_archivo(archivo) if archivo else None
    if del_titulo and del_archivo and del_titulo != del_archivo:
        raise ErrorInforme(f"El período del encabezado {del_titulo} no coincide con el del archivo {del_archivo}")
    fin = del_titulo or del_archivo
    if not fin:
        raise ErrorInforme("No se encontró el período del informe (ni en el encabezado ni en el nombre del archivo)")
    if not 1 <= fin[1] <= 12:
        raise ErrorInforme(f"Período desconocido: mes {fin[1]}")
    return trimestre_movil(*fin)


# ---------------------------------------------------------------- cuadros

def _leer_cuadro(n: int, filas: list[list[str]]) -> tuple[list[str], list[tuple[str, list[float]]]]:
    """Valida encabezado, filas y fuente de un cuadro; devuelve los indicadores y (rótulo, valores)."""
    tipo, esperados = CUADROS[n]
    if not filas:
        raise ErrorInforme(f"Cuadro {n + 1}: vacío")
    cab, *cuerpo = filas
    if plegar(cab[0]) != tipo:
        raise ErrorInforme(f"Cuadro {n + 1}: encabezado desconocido en la primera columna: {cab[0]!r}")
    columnas = []
    for c in cab[1:]:
        if IGNORADAS.get(plegar(c)) == n + 1:
            columnas.append(None)
        elif plegar(c) in COLUMNAS:
            columnas.append(COLUMNAS[plegar(c)])
        else:
            raise ErrorInforme(f"Cuadro {n + 1}: Encabezado desconocido: {c!r}")
    if [c for c in columnas if c] != esperados:
        raise ErrorInforme(f"Cuadro {n + 1}: Encabezado desconocido: {cab!r} (se esperaban {esperados})")
    if cuerpo and len(cuerpo[-1]) == 1 and plegar(cuerpo[-1][0]).startswith("fuente: ine"):
        cuerpo = cuerpo[:-1]  # fila de fuente al pie
    else:
        raise ErrorInforme(f"Cuadro {n + 1}: falta la fila de fuente al pie")
    datos = []
    for fila in cuerpo:
        if len(fila) != len(cab):
            raise ErrorInforme(f"Cuadro {n + 1}: fila con {len(fila)} celdas en vez de {len(cab)}: {fila!r}")
        datos.append((fila[0], [numero(v) for v, c in zip(fila[1:], columnas) if c]))
    return esperados, datos


def parsear_informe(html: str, archivo: str | None = None) -> pd.DataFrame:
    """Una fila por territorio e indicador, con el período del informe (AC-L5…L10).

    Columnas: territorio_id, nivel, codigo, indicador, valor, unidad, cuadro, es_estimado y las del período
    (periodo, periodo_inicio, periodo_fin, tipo_periodo).
    """
    ts, texto = leer_html(html)
    periodo = periodo_del_informe(html, archivo, texto)
    if len(ts) != len(CUADROS):
        raise ErrorInforme(f"Se esperaban {len(CUADROS)} cuadros y el informe trae {len(ts)}")

    cuadros = [_leer_cuadro(n, t) for n, t in enumerate(ts)]
    # La fila de total va primera, y los tres cuadros de un mismo nivel la traen o no la traen.
    con_total = [bool(d) and plegar(d[0][0]) in (TOTAL_PAIS, TOTAL_MVD) for _, d in cuadros]
    if len(set(con_total[:3])) > 1 or len(set(con_total[3:])) > 1:
        raise ErrorInforme(f"Los cuadros de un mismo nivel no coinciden en la fila de total: {con_total}")

    filas, total_mvd = [], {}
    for n, (indicadores, datos) in enumerate(cuadros):
        tipo, _ = CUADROS[n]
        rotulos = [plegar(r) for r, _ in datos]
        esperadas = (19 if tipo == "departamento" else 8) + con_total[n]
        if len(datos) != esperadas:
            raise ErrorInforme(f"Cuadro {n + 1}: {len(datos)} filas de datos, se esperaban {esperadas}")
        total = TOTAL_PAIS if tipo == "departamento" else TOTAL_MVD
        if {TOTAL_PAIS, TOTAL_MVD} & set(rotulos[con_total[n]:]) or (con_total[n] and rotulos[0] != total):
            raise ErrorInforme(f"Cuadro {n + 1}: fila de total fuera de lugar")

        vistos = set()
        for (rotulo, valores), r in zip(datos, rotulos):
            if r == TOTAL_MVD:
                total_mvd.update(zip(indicadores, valores))
                continue
            if r == TOTAL_PAIS:
                nivel, codigo = "pais", "UY"
            elif tipo == "departamento":
                nivel, codigo = "departamento", codigo_departamento(rotulo)
            else:
                nivel, codigo = "municipio_mvd", rotulo.strip().upper()
                if codigo not in MUNICIPIOS:
                    raise ErrorInforme(f"Cuadro {n + 1}: municipio desconocido: {rotulo!r}")
            if codigo in vistos:
                raise ErrorInforme(f"Cuadro {n + 1}: {rotulo!r} aparece dos veces")
            vistos.add(codigo)
            for ind, v in zip(indicadores, valores):
                filas.append({"territorio_id": tid(nivel, codigo), "nivel": nivel, "codigo": codigo,
                              "indicador": ind, "valor": v, "unidad": INDICADORES[ind], "cuadro": n + 1,
                              "es_estimado": False, **periodo.columnas()})

    df = pd.DataFrame(filas)
    # «Total Montevideo» no se guarda: tiene que repetir exactamente al departamento 01 (AC-L5).
    mvd = df[df.territorio_id == tid("departamento", "01")].set_index("indicador").valor
    distintos = {i: (v, mvd.get(i)) for i, v in total_mvd.items() if mvd.get(i) != v}
    if distintos:
        raise ErrorInforme(f"«Total Montevideo» no coincide con el departamento Montevideo: {distintos}")
    return df

