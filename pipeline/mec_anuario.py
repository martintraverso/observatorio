"""Parser del Anuario Estadístico de Educación del MEC (F4.3a, #179).

Lee los cuadros tal como se publican, sin red, guiado por el registro `fuentes/mec_anuario_educacion.yml`:

- `estructura(celdas, combinadas, hoja)`: código, título, año del título, rutas de encabezado por columna (las
  filas combinadas aplanadas, p. ej. «FORMA DE ADMINISTRACIÓN/PÚBLICA/SEXO/V»), filas y pie. Es el mismo algoritmo
  con el que `scripts/inventario_mec.py` escribe el registro: las rutas del parser y las del registro coinciden por
  construcción, y un test lo comprueba sobre los fixtures.
- `parsear_cuadro(xlsx, codigo, anio, mapeo, tipo)`: los valores de un cuadro, con el mapeo por columna del registro
  (`[{col, ruta, id, omitir?, anio?}]`). Falla (`ErrorAnuario`) ante una fila desconocida en un cuadro tipo A, una
  columna con datos que el mapeo no tiene, una columna mapeada cuya ruta no está en el archivo o un año de título
  distinto del del archivo (AC-E8–E10).
- `parsear_serie_matricula(xlsx)`: la hoja «MATRÍCULA DEL SISTEMA 2002-<año>» en `pais/UY` × año (AC-E14).

Valores (AC-E11): conteos enteros como se publican (también los guardados como texto, II-2.3.2). «-», «…», «s/d»,
«n/c» y las celdas vacías no son datos: no generan fila y se cuentan. Pie (AC-E12): las filas «Fuente:» y «Nota:»
quedan en el resultado, ligadas al código del cuadro, y nunca se leen como datos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd
from territorios_2023 import NOMBRES_DEPTO, tid

from comun.periodos import anio as periodo_anio
from comun.xlsx import leer_hoja, nombres_de_hojas

PAIS = tid("pais", "UY")
INTERIOR = tid("region", "interior")
FILAS_PAIS = {"total", "total del pais"}  # «TOTAL DEL PAÍS» en 30 cuadros-año (inventario de F4.1)
SERIE = "MATRÍCULA DEL SISTEMA"
NO_DATO = re.compile(r"^\s*(-+|…|\.\.\.|\.|s/d|n/c|s/i)?\s*\**\s*$", re.I)  # «n/c *»: con llamada de nota


class ErrorAnuario(ValueError):
    """El cuadro no coincide con su mapeo o con lo que se espera: la corrida falla en vez de cargar datos dudosos."""


def plegar(t) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", str(t)) if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def slug(t) -> str:
    return re.sub(r"[^a-z0-9]+", "_", plegar(t)).strip("_")


def letra(columna: int) -> str:
    s = ""
    while columna:
        columna, r = divmod(columna - 1, 26)
        s = chr(65 + r) + s
    return s


def numero(v):
    """Valor numérico de una celda; los números guardados como texto («7466», II-2.3.2) también cuentan. Un float
    entero (así guarda el xlsx los conteos) queda como int."""
    if isinstance(v, bool):
        return None
    if isinstance(v, float):
        return int(v) if v.is_integer() else v
    if isinstance(v, int):
        return v
    if isinstance(v, str) and re.fullmatch(r"\s*\d+(\.\d+)?\s*", v):
        return float(v) if "." in v else int(v)
    return None


def _valor(v):
    """Celda como la ve el algoritmo de encabezados: textos tal cual, números enteros como int."""
    return numero(v) if isinstance(v, float) else v


DEPARTAMENTOS = {plegar(n): tid("departamento", c) for c, n in NOMBRES_DEPTO.items()}


def territorio_de_fila(rotulo: str) -> str | None:
    """Rótulo de fila de un cuadro tipo A → territorio (AC-E8); None si no es un territorio conocido. Una llamada
    de nota al final («Colonia*», «Salto (1)», II-3.1.1 2020) no es parte del nombre."""
    p = re.sub(r"\s*(\*+|\(\d+\)|\d+)$", "", plegar(rotulo))
    if p in FILAS_PAIS:
        return PAIS
    if p == "resto del pais":
        return INTERIOR
    return DEPARTAMENTOS.get(p)


# ---------------------------------------------------------------- estructura de un cuadro

def es_titulo(v: str, titulo: str) -> bool:
    t = " ".join(v.split())
    return t == " ".join(titulo.split()) or bool(re.search(r"\(Todo el pa[ií]s", t)) or len(t) > 120


def completar_grupos(combinadas, hdr: dict, desde: int, hasta: int, max_col: int) -> list[str]:
    """Celdas vacías de encabezado bajo un grupo combinado más angosto que sus columnas. Dos casos, según el rótulo
    propio de la columna (el primero que tiene más abajo):
    - un total («TOTAL») abre el grupo de su **derecha**: en II-2.2.13, E8 «TOTAL» es el total de NO PROMOVIDOS
      (F7:G7); en II-4.2.2, H10 «TOTAL» es el de BACHILLERATO FIGARI (I8:J8);
    - otro rótulo cierra el grupo de su **izquierda**: en II-1.1.1 de 2020, «PÚBLICA» está en C7:F7 pero G8
      («Jardines de Tiempo Completo») también es pública (D+E+F+G = «Total Público»).
    Solo grupos de más de una columna que no sean ellos mismos un total, sin encadenar, y con el mismo padre en la
    fila de arriba. Hay casos que esta regla etiqueta mal: se mapean a mano en el registro (D5, F4.3b). Devuelve las
    celdas completadas."""
    por_fin = {(f1, c2): (f1, c1) for f1, c1, f2, c2 in combinadas if c2 > c1}
    por_inicio = {(f1, c1): (f1, c1) for f1, c1, f2, c2 in combinadas if c2 > c1}
    originales = dict(hdr)
    hechas = []
    for r in range(desde, hasta + 1):
        for c in range(2, max_col + 1):
            if originales.get((r, c)) is not None:
                continue
            propio = next((originales[(x, c)] for x in range(r + 1, hasta + 1) if originales.get((x, c)) is not None), None)
            if propio is None:
                continue
            vecino = c + 1 if plegar(propio).startswith("total") else c - 1
            m = (por_inicio if vecino > c else por_fin).get((r, vecino))
            if m is None or plegar(originales.get(m, "total")).startswith("total"):
                continue
            if r > desde and originales.get((r - 1, c)) != originales.get((r - 1, vecino)):
                continue
            hdr[(r, c)] = originales[m]
            lado = "derecha" if vecino > c else "izquierda"
            hechas.append(f"{letra(c)}{r} ← «{' '.join(str(hdr[(r, c)]).split())}» ({lado})")
    return hechas


@dataclass
class Estructura:
    codigo: str
    hoja: str
    titulo: str
    anio_titulo: int | None
    encabezado_sup: str
    sin_datos: bool = False
    rutas: dict[int, str] = field(default_factory=dict)  # columna → ruta
    filas: list[tuple[int, str]] = field(default_factory=list)  # (fila, rótulo) de los datos
    pie: list[str] = field(default_factory=list)
    heredadas: list[str] = field(default_factory=list)


def estructura(celdas: dict[tuple[int, int], object], combinadas, hoja: str) -> Estructura | None:
    """Estructura de un cuadro a partir de sus celdas ({(fila, col): valor}, sin vacías) y celdas combinadas."""
    if not celdas:
        return None
    cod = fila_cod = None
    for (r, c), v in sorted(celdas.items()):
        if isinstance(v, str) and (m := re.search(r"Cuadro\s*(?:N[ºo°]\s*)?(II-\s*[\d.]+)", v)):
            cod, fila_cod = re.sub(r"\s+", "", m.group(1)).strip("."), r
            break
    nombre = hoja.strip()
    if not cod:  # sin «Cuadro …» en la hoja (II-8.4.1, II-8.4.3): el código es el nombre de la hoja
        cod, fila_cod = nombre, min(r for r, _ in celdas)
    elif cod != nombre:
        cod = nombre
    textos = [v for (r, c), v in sorted(celdas.items()) if r > fila_cod and isinstance(v, str)
              and not v.lstrip().startswith(("Nota", "Fuente"))]
    # título: el que dice el año («…, 2024)»); si ninguno lo dice (II-2.3.2), el primer texto largo
    titulo = next((v for v in textos if re.search(r"\(.*\d{4}\)", v)), None) or next((v for v in textos if len(v) > 40), "")
    fila_tit = next((r for (r, c), v in sorted(celdas.items()) if v == titulo), fila_cod)
    anios_tit = re.findall(r"(\d{4})\)", titulo)
    sup = " ".join(str(v) for (r, c), v in sorted(celdas.items()) if r < fila_cod and isinstance(v, str))
    e = Estructura(cod, hoja, " ".join(titulo.split()), int(anios_tit[-1]) if anios_tit else None, sup)
    filas = sorted({r for r, _ in celdas})
    desde = next((r for r in filas if r > fila_tit and isinstance(celdas.get((r, 1)), str)
                  and any(numero(celdas.get((r, c))) is not None for c in range(2, 60))), None)
    if desde is None:
        e.sin_datos = True
        e.pie = [" ".join(str(v).split()) for (r, c), v in sorted(celdas.items()) if isinstance(v, str) and re.match(r"\s*Nota", v)]
        return e
    hdr = {}
    for f1, c1, f2, c2 in combinadas:
        v = celdas.get((f1, c1))
        if v is not None:
            for r in range(max(f1, fila_tit + 1), min(f2, desde - 1) + 1):
                for c in range(c1, c2 + 1):
                    hdr[(r, c)] = v
    for (r, c), v in celdas.items():
        if fila_tit < r < desde:
            hdr.setdefault((r, c), v)
    num_cols = [c for (r, c), v in celdas.items() if r >= desde and numero(v) is not None]
    max_col = max(num_cols) if num_cols else 1
    e.heredadas = completar_grupos(combinadas, hdr, fila_tit + 1, desde - 1, max_col)
    for c in range(2, max_col + 1):
        partes = []
        for r in range(fila_tit + 1, desde):
            v = hdr.get((r, c))
            n = numero(v)
            if v is None or (n is not None and n > 30) or (isinstance(v, str) and es_titulo(v, titulo)):
                continue  # conteos que se cuelan (II-3.2.8: 146, 190) y el título (II-2.2.16) no son rutas;
                # números chicos sí lo son: edades y grados (II-1.2.2: AÑOS/3, 4, 5, 6)
            if not partes or partes[-1] != " ".join(str(v).split()):
                partes.append(" ".join(str(v).split()))
        e.rutas[c] = "/".join(partes) or f"columna {c}"
    for r in [x for x in filas if x >= desde]:
        a = celdas.get((r, 1))
        if isinstance(a, str) and re.match(r"\s*(Fuente|Nota|Notas|\(\d|\*)", a):
            e.pie.append(" ".join(a.split()))
            continue
        if a is None and not any((r, c) in celdas for c in range(2, max_col + 1)):
            continue
        e.filas.append((r, " ".join(str(a).split()) if a is not None else ""))
    return e


def celdas_de(xlsx: bytes, hoja: str):
    filas, combinadas = leer_hoja(xlsx, hoja)
    return {(r, c): _valor(v) for r, cols in filas.items() for c, v in cols.items()}, combinadas


def hoja_del_cuadro(xlsx: bytes, codigo: str) -> str:
    for h in nombres_de_hojas(xlsx):
        if h.strip() == codigo:
            return h
    raise ErrorAnuario(f"El archivo no tiene la hoja del cuadro {codigo}")


# ---------------------------------------------------------------- valores de un cuadro

@dataclass
class Cuadro:
    codigo: str
    anio: int
    titulo: str
    datos: pd.DataFrame
    pie: list[str]
    sin_dato: int  # celdas mapeadas que no son datos («-», «…», «s/d», vacías): AC-E11
    avisos: list[str]


COLUMNAS = ["indicador", "territorio_id", "periodo", "periodo_inicio", "periodo_fin", "tipo_periodo", "valor",
            "codigo_cuadro", "celda"]


def parsear_cuadro(xlsx: bytes, codigo: str, anio: int, mapeo: list[dict], tipo: str) -> Cuadro:
    """Valores del cuadro `codigo` del anuario `anio`, con el mapeo por columna del registro.

    Tipo A: cada fila es un territorio (AC-E8). Tipo B y C: cada fila es una categoría que pasa a ser parte del
    indicador (`<id>__<categoría>`) y el valor va a `pais/UY` (D1), salvo bajo una fila «TOTAL MONTEVIDEO» o «TOTAL
    RESTO DEL PAÍS», que las lleva a ese territorio (la fila del total es la categoría `total`). Una entrada del mapeo con `anio` (D4: el pie
    declara que esa columna es de otro año) se guarda con ese período."""
    celdas, combinadas = celdas_de(xlsx, hoja_del_cuadro(xlsx, codigo))
    e = estructura(celdas, combinadas, codigo)
    if e is None or e.sin_datos:
        raise ErrorAnuario(f"{codigo} {anio}: el cuadro no tiene datos")
    avisos = []
    if e.anio_titulo is None:
        avisos.append(f"{codigo} {anio}: el título no dice el año; se usa el del archivo")
    elif e.anio_titulo != anio:
        raise ErrorAnuario(f"{codigo} {anio}: el título dice {e.anio_titulo} (AC-E10)")
    por_col = {m["col"]: m for m in mapeo}
    for c, ruta in e.rutas.items():
        hay_datos = any(numero(celdas.get((r, c))) is not None for r, _ in e.filas)
        m = por_col.get(letra(c))
        if m is None:
            if hay_datos:
                raise ErrorAnuario(f"{codigo} {anio}: la columna {letra(c)} «{ruta}» no está en el mapeo (AC-E9)")
            continue
        if m["ruta"] != ruta:
            raise ErrorAnuario(f"{codigo} {anio}: el mapeo dice «{m['ruta']}» en {letra(c)} y el archivo «{ruta}» (AC-E9)")
    columnas = {_col(m["col"]) for m in mapeo}
    if faltan := sorted(columnas - set(e.rutas)):
        raise ErrorAnuario(f"{codigo} {anio}: columnas mapeadas que el archivo no tiene: {[letra(c) for c in faltan]} (AC-E9)")
    filas, sin_dato, pie, ignoradas = [], 0, list(e.pie), 0
    cols_mapeadas = [_col(m["col"]) for m in mapeo]
    grupo, territorio_grupo = "", PAIS
    for r, rotulo in e.filas:
        vacia = all(celdas.get((r, c)) is None for c in cols_mapeadas)
        territorio = territorio_de_fila(rotulo) if tipo == "A" else None
        if vacia and territorio is None:
            # fila sin nada en las columnas mapeadas y que no es un territorio: continuación de una nota («2- Dentro
            # de …», «Los datos refieren …») o restos fuera del cuadro (II-2.3.1: números sueltos en la columna A)
            if len(rotulo) >= 20 and numero(rotulo) is None:
                pie.append(rotulo)
            else:
                ignoradas += 1
            continue
        # una fila con algo en las columnas mapeadas (aunque sea «s/d») es una fila de datos: se valida entera
        es_total = tipo != "A" and (plegar(rotulo) in FILAS_PAIS or plegar(rotulo).startswith("total "))
        if es_total:
            # B/C: una fila «TOTAL …» abre un grupo. Si nombra un territorio, las filas del grupo van a ese territorio
            # (mantenedor, #180): «TOTAL DEL PAÍS» → país, «TOTAL MONTEVIDEO» → departamento/01, «TOTAL RESTO DEL
            # PAÍS» → region/interior (= TOTAL − MONTEVIDEO). Si no, el grupo pasa a ser parte de la categoría.
            nombrado = PAIS if plegar(rotulo) in FILAS_PAIS else territorio_de_fila(rotulo.split(None, 1)[1])
            grupo, territorio_grupo = ("", nombrado) if nombrado else (rotulo, PAIS)
        if tipo == "A":
            if territorio is None:
                raise ErrorAnuario(f"{codigo} {anio}: fila desconocida «{rotulo}» (AC-E8)")
            sufijo = ""
        else:
            categoria = "total" if es_total and not grupo else (rotulo if not grupo or rotulo == grupo else f"{grupo}/{rotulo}")
            territorio, sufijo = territorio_grupo, f"__{slug(categoria) or 'sin_rotulo'}"
        for m in mapeo:
            if m.get("omitir"):
                continue  # repite otra columna que ya se carga (D7)
            c = _col(m["col"])
            v = numero(celdas.get((r, c)))
            if v is None:
                bruto = celdas.get((r, c))
                if bruto is not None and not (isinstance(bruto, str) and NO_DATO.match(bruto)):
                    raise ErrorAnuario(f"{codigo} {anio}: valor no numérico {bruto!r} en {letra(c)}{r}")
                sin_dato += 1
                continue
            per = periodo_anio(int(m.get("anio", anio))).columnas()
            filas.append({"indicador": m["id"] + sufijo, "territorio_id": territorio, **per, "valor": v,
                          "codigo_cuadro": codigo, "celda": f"{letra(c)}{r}"})
    datos = pd.DataFrame(filas, columns=COLUMNAS)
    if tipo == "A" and len(datos):
        # II-2.2.18 de 2023: todos los territorios «s/d» y el TOTAL en 0. El 0 es una fórmula que suma celdas sin
        # dato, no un cero publicado: se cuenta como falta de dato y no se carga.
        por_ind = datos.groupby("indicador").territorio_id.agg(set)
        falsos = [i for i, t in por_ind.items() if t == {PAIS} and (datos.loc[datos.indicador == i, "valor"] == 0).all()]
        if falsos:
            sin_dato += len(falsos)
            avisos.append(f"{codigo} {anio}: total en 0 sin ningún territorio con dato, no se carga: {falsos[:3]}")
            datos = datos[~datos.indicador.isin(falsos)].reset_index(drop=True)
    repetidas = datos.duplicated(["indicador", "territorio_id", "periodo"], keep=False)
    if repetidas.any():
        raise ErrorAnuario(f"{codigo} {anio}: valores repetidos para un mismo indicador y territorio: "
                           f"{datos.loc[repetidas, 'celda'].tolist()[:6]}")
    if ignoradas:
        avisos.append(f"{codigo} {anio}: {ignoradas} filas sin datos ignoradas")
    return Cuadro(codigo, anio, e.titulo, datos, pie, sin_dato, avisos)


def _col(letras: str) -> int:
    n = 0
    for ch in letras:
        n = n * 26 + ord(ch) - 64
    return n


# ---------------------------------------------------------------- serie nacional

NIVEL_ADMIN = {"publica", "privada"}


def _rotulo_serie(t: str) -> str:
    """Sin espacios de más ni la llamada de nota final («Común pública 2», «Privada3»)."""
    return re.sub(r"(?<=[^\d\s])\s*\d$", "", " ".join(str(t).split()))


def parsear_serie_matricula(xlsx: bytes) -> pd.DataFrame:
    """La hoja «MATRÍCULA DEL SISTEMA 2002-<año>» en `pais/UY` × año (AC-E14): una fila por año, nivel y forma de
    administración. El rótulo puede estar en la columna 1, 2 o 3 (sangría = nivel); «Pública» y «Privada» desglosan
    la fila anterior. El indicador es `edu_serie_<ruta>` (p. ej. `edu_serie_total_educacion_primaria_primaria_comun`)."""
    hoja = next((h for h in nombres_de_hojas(xlsx) if h.strip().startswith(SERIE)), None)
    if hoja is None:
        raise ErrorAnuario("El archivo no tiene la hoja de la serie nacional")
    filas, _ = leer_hoja(xlsx, hoja)
    fila_anios = next((r for r in sorted(filas) if sum(1 for v in filas[r].values()
                       if isinstance(v, float) and 2000 <= v <= 2100 and v.is_integer()) >= 5), None)
    if fila_anios is None:
        raise ErrorAnuario("La serie nacional no tiene la fila de años")
    anios = {c: int(v) for c, v in filas[fila_anios].items() if isinstance(v, float) and 2000 <= v <= 2100}
    ruta: dict[int, str] = {}
    ultima = None
    salida = []
    sin_dato = 0
    for r in sorted(x for x in filas if x > fila_anios):
        rot = next(((c, v) for c, v in sorted(filas[r].items()) if c <= 3 and isinstance(v, str) and v.strip()), None)
        valores = {c: numero(v) for c, v in filas[r].items() if c in anios}
        if rot is None or not any(v is not None for v in valores.values()):
            continue
        nivel, texto = rot[0], _rotulo_serie(rot[1])
        if plegar(texto) in NIVEL_ADMIN and ultima is not None:
            camino = f"{ultima}/{texto}"
        else:
            ruta = {k: v for k, v in ruta.items() if k < nivel}
            ruta[nivel] = texto
            camino = ultima = "/".join(ruta[k] for k in sorted(ruta))
        for c, v in valores.items():
            if v is None:
                bruto = filas[r].get(c)
                if bruto is not None and not (isinstance(bruto, str) and NO_DATO.match(bruto)):
                    raise ErrorAnuario(f"Serie nacional: valor no numérico {bruto!r} en {letra(c)}{r}")
                sin_dato += 1
            else:
                salida.append({"indicador": f"edu_serie_{slug(camino)}", "territorio_id": PAIS, **periodo_anio(anios[c]).columnas(),
                               "valor": v, "codigo_cuadro": SERIE, "celda": f"{letra(c)}{r}", "ruta": camino})
    datos = pd.DataFrame(salida)
    if datos.duplicated(["indicador", "periodo"]).any():
        raise ErrorAnuario("La serie nacional repite un indicador y año")
    datos.attrs["sin_dato"] = sin_dato  # «S/D», «n/c» (AC-E11)
    return datos
