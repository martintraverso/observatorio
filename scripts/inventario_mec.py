"""F4.1 (#164): inventario de los anuarios del MEC 2020–2024 y registro de la fuente.

Herramienta de exploración (no corre en el pipeline ni en CI). Lee los xlsx con `pipeline/comun/xlsx.py` y la estructura de
cada cuadro con `pipeline/mec_anuario.py` (la del parser). Pide cada anuario a su URL (siempre; lo guarda en `<dir>/<año>.xlsx`) y escribe:

- `docs/investigacion/mec_anuario_inventario.md`: archivos, cuadros × años con tipo (A/B/C) y ola, cambios de
  significado entre años y anomalías;
- `fuentes/mec_anuario_educacion.yml`: página, una entrada por año (URL, sha256, fechas) y cada cuadro con tipo,
  ola y años; para los de la ola 1, el mapeo por año ruta de encabezado → indicador y unidad.

Tipo (D1): A = filas por departamento (TOTAL / MONTEVIDEO / RESTO DEL PAÍS / 18 departamentos); C = filas por otra
unidad (institución, sede, centro); B = solo totales del país por categoría. La clasificación es automática por los
rótulos de fila: el inventario la marca para revisar.

Ids de indicador: `edu_<código>_<ruta>` (p. ej. `edu_ii_2_2_1_forma_de_administracion_publica_total`). Una columna
cuyo significado cambia entre años sin cambiar su ruta (II-2.2.1: en 2024 el sexo «total» es solo pública) recibe
un sufijo propio en ese año (`_solo_publica`), para que nunca se mezclen (AC-E13), y `omitir`: repite la columna de
pública, que ya se carga.

Uso: python scripts/inventario_mec.py [--dir datos/crudo/mec_anuario]
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import html
import re
import sys
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import mec_anuario as mec  # noqa: E402

from comun.xlsx import nombres_de_hojas  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
PAGINA = "https://www.gub.uy/ministerio-educacion-cultura/datos-y-estadisticas/datos"
PAGINA_ANIO = PAGINA + "/anuario-estadistico-educacion-{anio}"
OFICIAL = "https://www.gub.uy/ministerio-educacion-cultura/"
ANIOS = [2020, 2021, 2022, 2023, 2024]
AGENTE = "Mozilla/5.0 (observatorio-uruguay; inventario)"
DEPTOS = {"artigas", "canelones", "cerro largo", "colonia", "durazno", "flores", "florida", "lavalleja", "maldonado",
          "paysandu", "rio negro", "rivera", "rocha", "salto", "san jose", "soriano", "tacuarembo", "treinta y tres",
          "montevideo"}
INSTITUCION = re.compile(r"universidad|instituto|facultad|centro|utu|ifd|cerp|sede|escuela|liceo|udelar|utec")
CODIGO_HOJA = re.compile(r"^\s*II-\d+\.\d+\.\d+\s*$")


numero, plegar, slug = mec.numero, mec.plegar, mec.slug


def ola(codigo: str) -> int:
    """Ola 1 de D1 (docs/PLAN_educacion.md), a confirmar con los títulos."""
    n = tuple(int(x) for x in codigo[3:].split("."))
    if n[:2] in {(1, 2), (2, 3), (3, 1), (3, 2), (4, 2)}:
        return 1
    if n in {(1, 1, 1), (1, 1, 2), (2, 2, 1), (4, 1, 1)} or n[:2] == (2, 1) and n[2] <= 4:
        return 1
    if n[:2] == (2, 2) and 13 <= n[2] <= 18:
        return 1
    # F4.8a1 (#224): la ola 2 de inicial y primaria (II-1.3.x, II-2.2.2–II-2.2.12) se suma a la carga
    if n[:2] in {(1, 3), (2, 2)}:
        return 1
    return 2


def unidad(texto: str) -> str:
    t = plegar(texto)
    for clave, u in (("docente", "docentes"), ("personal academico", "docentes"), ("grupo", "grupos"), ("establecimiento", "establecimientos"),
                     ("egresad", "estudiantes"), ("estudiante", "estudiantes"), ("matricul", "estudiantes"),
                     ("rendimiento", "estudiantes"), ("promovid", "estudiantes"), ("asistencia", "estudiantes")):
        if clave in t:
            return u
    return "?"


def pedir(url: str) -> tuple[int, bytes]:
    """Estado HTTP y contenido; solo del sitio oficial del MEC, también después de redirecciones."""
    if not url.startswith(OFICIAL):
        raise SystemExit(f"URL fuera del sitio oficial del MEC: {url}")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENTE}), timeout=180) as r:
        if not r.geturl().startswith(OFICIAL):
            raise SystemExit(f"{url} redirige fuera del sitio oficial: {r.geturl()}")
        return r.status, r.read()


def bajar(url: str) -> bytes:
    return pedir(url)[1]


def archivo_del_anio(anio: int) -> dict:
    """URL del xlsx y fechas, leídas de la página del anuario (nunca se arma la URL)."""
    pag = PAGINA_ANIO.format(anio=anio)
    t = bajar(pag).decode("utf-8")
    urls = sorted(set(re.findall(r'https://www\.gub\.uy/ministerio-educacion-cultura/sites/[^"]+\.xlsx', t)))
    if len(urls) != 1:
        raise SystemExit(f"{anio}: la página enlaza {len(urls)} xlsx; se espera uno")
    texto = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", "", t, flags=re.S))).split())
    pub = re.search(r"Datos (\d{2}/\d{2}/\d{4})", texto)
    act = re.search(r"Actualiz\w* (\d{1,2}(?:/| de )\w+(?:/| )\d{4})", texto)
    return {"pagina": pag, "url": urls[0], "publicado": pub.group(1) if pub else None, "actualizado": act.group(1) if act else None}


def cuadro(xlsx: bytes, hoja: str) -> dict | None:
    """Lo que el inventario y el registro necesitan de un cuadro. La estructura (código, título, rutas de encabezado,
    filas y pie) sale de `pipeline/mec_anuario.py`, la misma que usa el parser: las rutas del registro y las que
    lee la carga coinciden por construcción."""
    celdas, combinadas = mec.celdas_de(xlsx, hoja)
    e = mec.estructura(celdas, combinadas, hoja)
    if e is None:
        return None
    base = {"codigo": e.codigo, "hoja": hoja, "titulo": e.titulo,
            "unidad": unidad(e.titulo) if unidad(e.titulo) != "?" else unidad(e.encabezado_sup), "anio_titulo": e.anio_titulo}
    if e.sin_datos:
        return {**base, "tipo": None, "sin_datos": True, "pie": e.pie}
    rotulos = [x for _, x in e.filas]
    valores, no_num, como_texto = {}, 0, 0
    for r, _ in e.filas:
        for c in e.rutas:
            v = celdas.get((r, c))
            n = numero(v)
            valores.setdefault(c, []).append(n)
            no_num += n is None
            como_texto += n is not None and isinstance(v, str)
    pl = [plegar(x) for x in rotulos]
    # la misma regla de territorios que el parser: «MONTEVIDEO*» (II-3.1.2 2020) también es Montevideo
    terr = [mec.territorio_de_fila(x) for x in rotulos]
    deptos = sum(1 for t in terr if t and "/departamento/" in t)
    tipo = ("A" if mec.PAIS in terr and mec.tid("departamento", "01") in terr and deptos >= 15
            else "C" if any(INSTITUCION.search(x) for x in pl) else "B")
    # columnas con otra ruta pero los mismos valores en todas las filas: posible cambio de significado
    iguales = []
    cols = [c for c in e.rutas if any(v is not None for v in valores.get(c, []))]
    for i, c1 in enumerate(cols):
        for c2 in cols[i + 1:]:
            if valores[c1] == valores[c2] and "SEXO" not in e.rutas[c1].upper().split("/")[:1]:
                iguales.append((e.rutas[c1], e.rutas[c2]))
    return {**base, "tipo": tipo, "rutas": [e.rutas[c] for c in sorted(e.rutas)],
            "columnas": [mec.letra(c) for c in sorted(e.rutas)], "filas": len(rotulos),
            "rotulos": rotulos, "resto": "resto del pais" in pl, "pie": e.pie, "no_numericas": no_num,
            "como_texto": como_texto, "iguales": iguales, "heredadas": e.heredadas,
            "valores": [valores.get(c, []) for c in sorted(e.rutas)],
            "total_como": next((r for r in rotulos if plegar(r) in ("total", "total del pais")), None)}


def extraer(d: Path) -> dict:
    res = {}
    for a in ANIOS:
        xlsx = (d / f"{a}.xlsx").read_bytes()
        hojas = nombres_de_hojas(xlsx)
        cuadros = []
        for h in hojas:
            if not CODIGO_HOJA.match(h):
                continue  # presentación, separadores de nivel (índices), CONTROL, Hoja1
            x = cuadro(xlsx, h)
            if x:
                cuadros.append(x)
        res[a] = {"hojas": hojas, "cuadros": {c["codigo"]: c for c in cuadros}}
        print(a, len(cuadros), "cuadros", file=sys.stderr)
    return res


def id_indicador(codigo: str, ruta: str, sufijo: str = "") -> str:
    return f"edu_{slug(codigo)}_{slug(ruta)}{sufijo}"


def mapear(codigo: str, columnas: list[str], rutas: list[str], solo_pub: dict[str, str]) -> list[dict]:
    """Una entrada por columna numérica: {col, ruta, id}. El id es único dentro del cuadro y año: dos columnas con
    la misma ruta (II-4.2.4: «SEXO/Varón» total, pública y privada, porque «PÚBLICA» no está combinada sobre ellas)
    o que solo difieren en mayúsculas (II-2.1.4: «TOTAL» y «Total») reciben `__2`, `__3`… en orden de columna.
    `repetida: true` las marca: su ruta no alcanza para saber qué son y hay que mapearlas a mano (F4.3)."""
    vistos: dict[str, int] = {}
    cuenta = {}
    for r in rutas:
        cuenta[slug(r)] = cuenta.get(slug(r), 0) + 1
    m = []
    for col, r in zip(columnas, rutas):
        i = id_indicador(codigo, r, "_solo_publica" if r in solo_pub else "")
        vistos[i] = vistos.get(i, 0) + 1
        e = {"col": col, "ruta": r, "id": i if vistos[i] == 1 else f"{i}__{vistos[i]}"}
        if cuenta[slug(r)] > 1:
            e["repetida"] = True
        if r in solo_pub:  # repite una columna de pública: ya está cargado, no se vuelve a cargar (mantenedor, #177)
            e["omitir"] = f"repite «{solo_pub[r]}»"
        m.append(e)
    return m


MANUAL = RAIZ / "fuentes" / "mec_anuario" / "mapeo_manual.yml"


def _suma(valores: list[list], cols: list[int]) -> list:
    return [sum((v[f] or 0) for v in (valores[c] for c in cols)) for f in range(len(valores[cols[0]]))]


def _igual(col: list, suma: list) -> bool:
    pares = [(a, b) for a, b in zip(col, suma) if a is not None]
    return bool(pares) and all(a == b for a, b in pares)


def _segs(r: str) -> list[str]:
    return r.split("/")


def _comun(a: str, b: str) -> int:
    n = 0
    for x, y in zip(_segs(a), _segs(b)):
        if plegar(x) != plegar(y):
            break
        n += 1
    return n


def resolver_repetidas(c: dict, estrategia: str, fila_con_error: str | None = None) -> tuple[dict[int, tuple[str, str]], list[str]]:
    """D5: para cada columna con ruta repetida, el concepto que suma (índice → (concepto, comprobación)). Solo se
    acepta lo que cierra con sumas en todas las filas; lo que no, vuelve en la lista de fallas."""
    rutas, valores = c["rutas"], c["valores"]
    cuenta: dict[str, int] = {}
    for r in rutas:
        cuenta[slug(r)] = cuenta.get(slug(r), 0) + 1
    rep = [i for i, r in enumerate(rutas) if cuenta[slug(r)] > 1]
    hechas, fallas = {}, []
    for i in rep:
        if all(v in (None, 0) for v in valores[i]):
            hechas[i] = (None, "columna vacía: separador del encabezado, sin datos")  # II-1.2.2
            continue
        if i == 0 and plegar(rutas[i]) == "total":
            # el total general (primera columna): suma de sus subcolumnas «TOTAL/…» o, si no hay, de todas las
            # columnas que no son totales (II-3.2.2 de 2020: B = suma de los V y M de cada curso)
            hijas = [j for j in range(1, len(rutas)) if rutas[j].startswith(rutas[i] + "/")]
            hojas = [j for j in range(1, len(rutas)) if not plegar(_segs(rutas[j])[-1]).startswith("total")
                     and plegar(rutas[j]) != "total"]
            for cols in (hijas, hojas):
                if not cols:
                    continue
                suma = _suma(valores, cols)
                distintas = [f for f, (x, y) in enumerate(zip(valores[i], suma)) if x is not None and x != y]
                tolerada = [f for f in distintas if fila_con_error and plegar(c["rotulos"][f]) == plegar(fila_con_error)]
                if len(distintas) == len(tolerada) and any(x is not None for x in valores[i]):
                    prueba = f"{c['columnas'][i]} = suma de {len(cols)} columnas ({c['columnas'][cols[0]]}…{c['columnas'][cols[-1]]})"
                    if distintas:  # II-3.2.2 2021 y 2022: Treinta y Tres no cierra en el archivo; se guarda lo publicado
                        f = distintas[0]
                        prueba += f"; salvo {c['rotulos'][f]}: {valores[i][f]} publicado contra {suma[f]} sumado (error de la fuente)"
                    hechas[i] = (rutas[i], prueba)
                    break
            else:
                # #224: II-2.2.12 empieza con el «TOTAL» de PROMOVIDOS, no con el total general: si el cuadro tiene
                # estrategia de vecino, se prueba esa (con su suma); si no, es una falla.
                if estrategia not in ("derecha", "izquierda"):
                    fallas.append(f"{c['columnas'][i]} «{rutas[i]}»: el total general no cierra")
                    continue
            if i in hechas:
                continue
        if estrategia in ("derecha", "izquierda"):
            paso = 1 if estrategia == "derecha" else -1
            v = i + paso
            if not 0 <= v < len(rutas):
                fallas.append(f"{c['columnas'][i]}: sin vecino a la {estrategia}")
                continue
            comun = _comun(rutas[i], rutas[v])
            # si la ruta de la columna es el comienzo de la del vecino, el grupo es ella misma (II-4.2.2 2020:
            # «TOTAL» y a su derecha «TOTAL/MUJER», «TOTAL/VARON»)
            grupo = rutas[i] if comun == len(_segs(rutas[i])) else "/".join(_segs(rutas[v])[:comun + 1])
            run = []
            while 0 <= v < len(rutas) and (rutas[v] == grupo or rutas[v].startswith(grupo + "/")) and v not in rep:
                run.append(v)
                v += paso
            if run and _igual(valores[i], _suma(valores, run)):
                cols = sorted(c["columnas"][j] for j in run)
                hechas[i] = (grupo if grupo == rutas[i] else f"{grupo}/TOTAL", f"{c['columnas'][i]} = " + " + ".join(cols))
            else:
                fallas.append(f"{c['columnas'][i]} «{rutas[i]}»: no es la suma del grupo «{grupo}»")
        elif estrategia == "padre":
            padre = next((j for j in range(i - 1, -1, -1) if j not in rep), None)
            ini = i
            while ini - 1 in rep:
                ini -= 1
            fin = i
            while fin + 1 in rep:
                fin += 1
            grupo = list(range(ini, fin + 1))
            # II-3.1.1: TOTAL PÚBLICOS = «Escuelas de CBT y Técnica» + «…/Reparticiones» (la columna que sigue)
            extendido = grupo + [j for j in range(fin + 1, len(rutas)) if j not in rep and rutas[j].startswith(rutas[fin] + "/")]
            if padre is not None and not _igual(valores[padre], _suma(valores, grupo)) and _igual(valores[padre], _suma(valores, extendido)):
                grupo = extendido
            if padre is not None and _igual(valores[padre], _suma(valores, grupo)):
                resto = "/".join(_segs(rutas[i])[_comun(rutas[padre], rutas[i]):])
                hechas[i] = (f"{rutas[padre]}/{resto}",
                             f"{c['columnas'][padre]} = " + " + ".join(c["columnas"][j] for j in grupo))
            else:
                fallas.append(f"{c['columnas'][i]} «{rutas[i]}»: las repetidas {[c['columnas'][j] for j in grupo]} no suman su columna padre")
        else:
            raise SystemExit(f"Estrategia desconocida: {estrategia}")
    return hechas, fallas


def anio_real(ex: dict, cod: str, a: int, regla: dict) -> tuple[dict[int, dict], list[str]]:
    """D4: índice de columna → {anio} o {omitir}; y la comparación con el anuario de ese año (para el inventario)."""
    c, real = ex[a]["cuadros"][cod], int(regla["anio"])
    otro = ex.get(real, {}).get("cuadros", {}).get(cod)
    filtro = plegar(regla["columnas"])
    cambios, notas = {}, []
    def clave(r):  # sin llamadas de nota: «PRIVADA*» (II-2.2.17 2022) es «PRIVADA» (2020)
        return plegar(re.sub(r"\*+", "", r))

    rutas_otro = {clave(r): k for k, r in enumerate(otro["rutas"])} if otro and not otro.get("sin_datos") else {}
    for i, r in enumerate(c["rutas"]):
        if filtro != "todas" and filtro not in plegar(r):
            continue
        k = rutas_otro.get(clave(regla.get("par", r)))
        if k is None:
            cambios[i] = {"anio": real}
            notas.append(f"{c['columnas'][i]} «{r}»: el anuario {real} no tiene esta columna para comparar; se carga como {real}")
            continue
        este = dict(zip(c["rotulos"], c["valores"][i]))
        aquel = dict(zip(otro["rotulos"], otro["valores"][k]))
        distintos = [f for f in este if f in aquel and este[f] != aquel[f]]
        if distintos:
            # el pie dice que son de otro año pero no coinciden con ese anuario (II-1.1.1 2022: la nota repite la
            # de 2021): no hay respaldo para cambiarles el año; se cargan en el del archivo y queda anotado
            notas.append(f"{c['columnas'][i]} «{r}»: el pie dice {real} pero difiere del anuario {real} en "
                         f"{len(distintos)} filas ({distintos[:3]}); se carga como {a}")
        else:
            cambios[i] = {"omitir": f"ya cargado desde el anuario {real}, con los mismos valores (D4)"}
    if not cambios and not notas:
        notas.append(f"ninguna columna coincide con «{regla['columnas']}»")
    return cambios, notas


SEXO = {"varon": "v", "varones": "v", "v": "v", "hombres": "v", "mujer": "m", "mujeres": "m", "m": "m"}
ENVOLTURA = {"publica", "forma de administracion", "tipo de curso", "educacion media basica tecnologica",
             "educacion media superior tecnologica", "modalidad", "rendimiento", "dges", "dgetp"}


def _norm(ruta: str) -> list[str]:
    """Segmentos comparables entre años: sin tildes ni mayúsculas, sin llamadas de nota, «SEXO» fuera y
    varón/varones/V → v, mujer/mujeres/M → m."""
    segs = [re.sub(r"\*+|\s*\d$|\.$", "", plegar(x)).strip() for x in ruta.split("/")]
    return [SEXO.get(x, x) for x in segs if x not in ("sexo", "por sexo")]


def conceptos_2024(cuadros: dict, manual: dict) -> None:
    """D6: cada columna de 2020–2023 de la ola 1 cuyo id no existe en 2024 pasa a usar el id de 2024 si significa lo
    mismo (`equivale_2024`), o queda con su id y un `motivo_d6`. Lo que 2024 agrupa en otra categoría no se suma
    (decisión del mantenedor): conserva su id con la nota de `reagrupaciones`.

    Una unión nunca cambia la cobertura por forma de administración (AC-E13): un curso sin administración se une a
    «PÚBLICA/…» de 2024 solo si ni 2023 ni 2024 tienen parte privada de ese curso; un total de un año sin columnas
    privadas no se une al de un año que sí las tiene; y una columna «PÚBLICA/…» no se une a una sin administración."""
    for cod, e in cuadros.items():
        mapeo = e.get("mapeo") or {}
        m24 = [x for x in mapeo.get(2024) or [] if not x.get("omitir")]
        if e["ola"] != 1 or not m24:
            continue
        ids24 = {x["id"] for x in mapeo[2024]}
        s24 = [(_norm(x.get("concepto", x["ruta"])), x["id"]) for x in m24]
        omitidas24 = [_norm(x.get("concepto", x["ruta"])) for x in mapeo[2024] if x.get("omitir")]
        recientes = [_norm(x.get("concepto", x["ruta"])) for a in (2023, 2024) for x in mapeo.get(a) or []]
        con_privada_reciente = any("privada" in t or "total privados" in t for t in recientes)
        reag = manual.get("reagrupaciones", {}).get(cod, {})

        def sin_env(t):
            return [y for y in t if y not in ENVOLTURA]

        for a in (2020, 2021, 2022, 2023):
            m = mapeo.get(a) or []
            sin_privada = not any("privada" in _norm(x.get("concepto", x["ruta"])) or
                                  "total privados" in _norm(x.get("concepto", x["ruta"])) for x in m)
            propuestas = {}
            for k, x in enumerate(m):
                if x.get("omitir"):
                    continue
                s = _norm(x.get("concepto", x["ruta"]))
                s_sin = sin_env(s)
                es_total = any(y.startswith("total") for y in s)
                privada_reciente = any("privada" in t and [y for y in sin_env(t) if y != "privada"] == s_sin for t in recientes)
                # un total general (o de un curso con parte privada desde 2023) de un año sin columnas privadas
                cobertura = (sin_privada and con_privada_reciente and es_total and a < 2023
                             and (len([y for y in s_sin if y not in ("v", "m")]) <= 1 or privada_reciente)
                             # «TOTAL LICEOS PÚBLICOS» o «… PRIVADOS» dicen su cobertura: no cambia
                             and not any("public" in y or "privad" in y for y in s))
                if x["id"] in ids24:
                    if cobertura:  # mismo id que 2024 pero otra cobertura: id propio, como `_solo_publica` (AC-E13)
                        x["id"] = x["id"] + "_sin_privados"
                        x["motivo_d6"] = "concepto distinto (AC-E13): hasta 2022 el total no incluye privados; desde 2023 sí"
                    continue
                igual = [i for t, i in s24 if t == s]
                cand = [(t, i) for t, i in s24 if sin_env(t) == s_sin]
                if len(cand) > 1:  # desempate: el que conserva más segmentos de la ruta (p. ej. «dgetp»)
                    mejor = max(len(set(t) & set(s)) for t, _ in cand)
                    cand = [(t, i) for t, i in cand if len(set(t) & set(s)) == mejor]
                motivo = None
                if s in omitidas24:
                    motivo = "concepto distinto (AC-E13): en 2024 esta columna cambia de significado y no se carga (D7)"
                elif cobertura and (igual or cand):
                    motivo = "concepto distinto (AC-E13): hasta 2022 el total no incluye privados; desde 2023 sí"
                elif igual:
                    propuestas[k] = (igual[0], "misma columna, otro rótulo (tildes, plurales o llamadas de nota)")
                    continue
                elif len(cand) == 1:
                    t = cand[0][0]
                    if "publica" in t and "publica" not in s and privada_reciente and sin_privada:
                        motivo = "concepto distinto (AC-E13): hasta este año sin separar pública y privada; desde 2023 las separa"
                    elif "publica" in s and "publica" not in t:
                        motivo = "concepto distinto (AC-E13): este año es solo pública y 2024 cubre todas las administraciones"
                    else:
                        porque = ("en 2024 va bajo «PÚBLICA» y ni 2023 ni 2024 tienen parte privada: mismo concepto"
                                  if "publica" in t and "publica" not in s else "misma columna dentro de otro grupo del encabezado")
                        propuestas[k] = (cand[0][1], porque)
                        continue
                elif len(cand) > 1:
                    motivo = "ambigua: varias columnas de 2024 coinciden; conserva su id"
                if motivo is None:
                    nota = next((v for clave, v in reag.items() if clave in s), None)
                    if nota:
                        motivo = nota + " (no se suma: decisión del mantenedor)"
                    elif "publica" not in s and "privada" not in s and privada_reciente and sin_privada:
                        motivo = "concepto distinto (AC-E13): hasta este año sin separar pública y privada; desde 2023 las separa"
                    elif any(len(sin_env(t)) > len(s_sin) and sin_env(t)[:len(s_sin)] == s_sin for t, _ in s24):
                        motivo = "2024 publica este grupo con otro desglose (p. ej. por sexo): sin columna equivalente"
                    else:
                        motivo = "categoría o columna que 2024 no publica (discontinuada o reclasificada)"
                x["motivo_d6"] = motivo
            # dos columnas del mismo año no pueden ir al mismo id de 2024: esas conservan el suyo
            destinos = collections.Counter(i for i, _ in propuestas.values())
            for k, (i, porque) in propuestas.items():
                if destinos[i] > 1:
                    m[k]["motivo_d6"] = f"varias columnas de este año equivalen a «{i}»: conserva su id"
                    continue
                m[k].update({"id": i, "equivale_2024": porque})
            ids = [x["id"] for x in m]
            if len(set(ids)) != len(ids):
                raise SystemExit(f"{cod} {a}: ids repetidos después de D6")


def solo_publica(c: dict) -> dict[str, str]:
    """Rutas de «total» por sexo que ese año son solo pública (la privada sin sexo), con la ruta de pública que
    repiten: II-2.2.1 en 2024."""
    sin_sexo_privada = any("privada" in plegar(p) and "sexo" in plegar(p) for p in c.get("pie", []))
    if not sin_sexo_privada:
        return {}
    return {a: b for a, b in c.get("iguales", []) if "/TOTAL/" in a.upper() and "PÚBLICA" in b.upper()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", type=Path, default=RAIZ / "datos" / "crudo" / "mec_anuario")
    args = ap.parse_args(argv)
    args.dir.mkdir(parents=True, exist_ok=True)
    hoy = dt.date.today().isoformat()
    archivos = {}
    for a in ANIOS:
        info = archivo_del_anio(a)
        destino = args.dir / f"{a}.xlsx"
        http, datos = pedir(info["url"])  # siempre: el sha256 es el de lo que sirve hoy la URL
        if destino.exists() and destino.read_bytes() != datos:
            print(f"aviso: {destino} difiere de lo publicado; se reemplaza", file=sys.stderr)
        destino.write_bytes(datos)
        archivos[a] = {**info, "http": http, "sha256": hashlib.sha256(datos).hexdigest(), "bytes": len(datos), "revisado": hoy}
    ex = extraer(args.dir)
    cuadros = escribir_registro(ex, archivos)
    escribir_inventario(ex, archivos, cuadros)
    return 0


def escribir_inventario(ex: dict, archivos: dict, cuadros: dict) -> None:
    codigos = sorted({c for a in ex for c in ex[a]["cuadros"]}, key=lambda c: tuple(int(x) for x in c[3:].split(".")))
    L = ["# Inventario de los anuarios del MEC 2020–2024 (F4.1, #164)", "",
         "Generado por `scripts/inventario_mec.py`; no editar a mano. Tipo (D1): A por departamento, B totales del país",
         "por categoría, C por institución u otra unidad (clasificación automática por los rótulos de fila: revisar).", "",
         "## Archivos", "", "| Año | Publicado | Actualización | Bytes | sha256 | Hojas | Cuadros |", "|---|---|---|---:|---|---:|---:|"]
    for a in ANIOS:
        f = archivos[a]
        L.append(f"| [{a}]({f['url']}) | {f['publicado']} | {f['actualizado'] or '—'} | {f['bytes']:,} | `{f['sha256'][:16]}…` | "
                 f"{len(ex[a]['hojas'])} | {len(ex[a]['cuadros'])} |")
    L += ["", "## Cuadros × años", "", "Ola por cuadro y tipo por año; «·» = no está ese año; «∅» = sin datos numéricos ese año. La columna Tipo junta los años.", "",
          "| Código | Título (último año) | Tipo | Ola | Unidad | " + " | ".join(map(str, ANIOS)) + " |",
          "|---|---|---|---|---|" + "---|" * len(ANIOS)]
    for cod in codigos:
        ult = next(ex[a]["cuadros"][cod] for a in reversed(ANIOS) if cod in ex[a]["cuadros"])
        tipos = {ex[a]["cuadros"][cod]["tipo"] for a in ANIOS if cod in ex[a]["cuadros"] and ex[a]["cuadros"][cod]["tipo"]}
        celdas = ["∅" if cod in ex[a]["cuadros"] and ex[a]["cuadros"][cod].get("sin_datos")
                  else (ex[a]["cuadros"][cod]["tipo"] if cod in ex[a]["cuadros"] else "·") for a in ANIOS]
        titulo = re.sub(r"\s*\(Todo el país.*", "", ult["titulo"])[:90]
        L.append(f"| {cod} | {titulo} | {'/'.join(sorted(tipos)) or '—'} | {ola(cod)} | {ult['unidad']} | " + " | ".join(celdas) + " |")
    L += ["", "## Cambios de encabezado entre años (ola 1)", "",
          "Rutas de encabezado que aparecen o desaparecen de un año a otro. Que una ruta siga igual **no** garantiza que",
          "signifique lo mismo: ver la sección siguiente.", ""]
    for cod in codigos:
        if ola(cod) != 1:
            continue
        prev = None
        for a in ANIOS:
            c = ex[a]["cuadros"].get(cod)
            if not c or c.get("sin_datos"):
                continue
            r = {plegar(x): x for x in c["rutas"]}  # sin tildes ni mayúsculas: VARON = VARÓN
            if prev is not None and set(r) != set(prev[1]):
                L.append(f"- **{cod}**, {prev[0]} → {a}: " + "; ".join(
                    [f"+ `{r[x]}`" for x in sorted(set(r) - set(prev[1]))] + [f"− `{prev[1][x]}`" for x in sorted(set(prev[1]) - set(r))]))
            prev = (a, r)
    L += ["", "## Mismo encabezado, otro significado", "",
          "Columnas con distinta ruta e idénticos valores en todas las filas, junto a una nota de que la privada no informa",
          "sexo: el «total» por sexo es solo pública ese año (AC-E13). Llevan `omitir`: repiten pública, que ya se carga.", ""]
    for a in ANIOS:
        for cod, c in ex[a]["cuadros"].items():
            for ruta in sorted(solo_publica(c)):
                L.append(f"- **{cod} {a}:** `{ruta}` = pública (pie: «{next(p for p in c['pie'] if 'sexo' in plegar(p))}»)")
    L += ["", "## Anomalías", ""]
    for a in ANIOS:
        for cod, c in ex[a]["cuadros"].items():
            if not c.get("anio_titulo"):
                L.append(f"- **{cod} {a}:** el título no dice el año («{c['titulo'][:100]}»)")
            if c.get("como_texto"):
                L.append(f"- **{cod} {a}:** {c['como_texto']} valores numéricos guardados como texto")
            if c.get("total_como") and plegar(c["total_como"]) != "total":
                L.append(f"- **{cod} {a}:** la fila del país dice «{c['total_como']}»")
            for nota in c.get("pie", []):
                otro = [int(x) for x in re.findall(r"año (\d{4})", nota) if int(x) != a]
                if otro:
                    L.append(f"- **{cod} {a}:** el pie dice que los datos son de {otro[0]} («{nota[:100]}»)")
            if c.get("anio_titulo") and c["anio_titulo"] != a:
                L.append(f"- **{cod} {a}:** el título dice {c['anio_titulo']} («{c['titulo'][:100]}»)")
            if c.get("sin_datos"):
                L.append(f"- **{cod} {a}:** sin datos numéricos" + (f" ({'; '.join(c['pie'])[:140]})" if c.get("pie") else ""))
            if c.get("unidad") == "?":
                L.append(f"- **{cod} {a}:** unidad no reconocida en el título")
    L += ["", "## Mapeo a mano (F4.3b-1)", "",
          "Lo que aplica `fuentes/mec_anuario/mapeo_manual.yml` en la ola 1: columnas repetidas y totales mal",
          "etiquetados con su comprobación con sumas (D5), y columnas con datos de otro año (D4).", ""]
    for cod in codigos:
        e = cuadros.get(cod, {})
        for a, m in sorted((e.get("mapeo") or {}).items()):
            hechos = [x for x in (m or []) if "comprobado" in x or "anio" in x or (x.get("omitir") and "D4" in x["omitir"])
                      or (x.get("omitir") or "").startswith("columna vacía")]
            notas = (e.get("anio_real_notas") or {}).get(a, []) + (e.get("mapeo_manual_fallas") or {}).get(a, [])
            if not hechos and not notas:
                continue
            L.append(f"- **{cod} {a}:**")
            for x in hechos:
                que = (f"→ `{x['concepto']}` ({x['comprobado']})" if "concepto" in x
                       else f"año real {x['anio']}" if "anio" in x
                       else f"omitir: {x['omitir']}" if "omitir" in x else f"({x['comprobado']})")
                L.append(f"  - {x['col']} `{x['ruta']}` {que}")
            L += [f"  - ⚠ {n}" for n in notas]
    L += ["", "## Conceptos según el anuario 2024 (D6, F4.3b-2)", "",
          "Columnas de 2020–2023 de la ola 1 cuyo id no existe en 2024: las que significan lo mismo pasan a usar el id",
          "de 2024 (`equivale_2024`); las demás conservan su id con un `motivo_d6`. Lo que 2024 agrupa no se suma.", ""]
    for cod in codigos:
        e = cuadros.get(cod, {})
        if e.get("ola") != 1:
            continue
        eq, mot = [], collections.Counter()
        for a, m in sorted((e.get("mapeo") or {}).items()):
            for x in m or []:
                if "equivale_2024" in x:
                    eq.append(f"{a} {x['col']} `{x.get('concepto', x['ruta'])}` → `{x['id']}` ({x['equivale_2024']})")
                elif "motivo_d6" in x:
                    mot[x["motivo_d6"]] += 1
        if not eq and not mot:
            continue
        L.append(f"- **{cod}:** {len(eq)} equivalencias, {sum(mot.values())} con motivo")
        L += [f"  - {x}" for x in eq]
        L += [f"  - {n} × {k}" for k, n in mot.most_common()]
    L += ["", "## Encabezados completados (revisar)", "",
          "Celdas vacías de encabezado que heredaron un grupo combinado vecino, de la derecha si su rótulo es un total o",
          "de la izquierda si no (ver `completar_grupos`). Heurística: hay casos mal resueltos (PR #177), revisar.", ""]
    for a in ANIOS:
        for cod, c in ex[a]["cuadros"].items():
            if c.get("heredadas"):
                L.append(f"- **{cod} {a}:** " + "; ".join(c["heredadas"]))
    L += ["", "## Hojas por año", ""]
    for a in ANIOS:
        otras = [h.strip() for h in ex[a]["hojas"] if not CODIGO_HOJA.match(h)]
        L.append(f"- **{a}** ({len(ex[a]['hojas'])} hojas): {len(ex[a]['cuadros'])} cuadros y " + ", ".join(f"«{h}»" for h in otras))
    L += ["", "## Detalle por cuadro y año", "",
          "Título, tipo, filas, rutas de encabezado (celdas combinadas aplanadas) y pie completo (Fuente/Nota).", ""]
    for cod in codigos:
        L += [f"<details><summary><b>{cod}</b></summary>", ""]
        for a in ANIOS:
            c = ex[a]["cuadros"].get(cod)
            if not c:
                continue
            L.append(f"**{a}** · hoja «{c['hoja'].strip()}» · tipo {c.get('tipo') or '—'} · {c.get('filas', 0)} filas · {c['titulo']}")
            L.append("")
            L += [f"- `{r}`" for r in c.get("rutas", [])]
            L += [f"- *{x}*" for x in c.get("pie", [])]
            L.append("")
        L += ["</details>", ""]
    (RAIZ / "docs" / "investigacion").mkdir(parents=True, exist_ok=True)
    (RAIZ / "docs" / "investigacion" / "mec_anuario_inventario.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def escribir_registro(ex: dict, archivos: dict) -> None:
    manual = yaml.safe_load(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else {}
    codigos = sorted({c for a in ex for c in ex[a]["cuadros"]}, key=lambda c: tuple(int(x) for x in c[3:].split(".")))
    cuadros = {}
    for cod in codigos:
        presentes = [a for a in ANIOS if cod in ex[a]["cuadros"]]
        ult = ex[presentes[-1]]["cuadros"][cod]
        tipos = {a: ex[a]["cuadros"][cod]["tipo"] for a in presentes}  # AC-E2: tipo por año (None = sin datos)
        e = {"titulo": re.sub(r"\s*\(Todo el país.*", "", ult["titulo"]), "tipos": tipos,
             "ola": ola(cod), "unidad": ult["unidad"], "anios": presentes}
        if ola(cod) == 1:
            e["mapeo"] = {}
            for a in presentes:
                c = ex[a]["cuadros"][cod]
                notas_otro = [n for n in c.get("pie", []) if any(int(x) != a for x in re.findall(r"año (\d{4})", n))]
                if notas_otro:  # parte o todo el cuadro con datos de otro año: se cargan con el año real (D4)
                    e.setdefault("datos_de_otro_anio", {})[a] = notas_otro
                motivo = manual.get("cuadros_sin_cargar", {}).get(cod, {}).get(a) or (
                    "sin datos numéricos" if c.get("sin_datos") else
                    f"el título dice {c['anio_titulo']} (AC-E10: debe ser el año del archivo)"
                    if c.get("anio_titulo") and c["anio_titulo"] != a else None)
                if motivo:  # AC-E2: lo que no se carga figura con su motivo
                    e["mapeo"][a] = None
                    e.setdefault("sin_cargar", {})[a] = motivo
                    continue
                sp = solo_publica(c)
                m = mapear(cod, c["columnas"], c["rutas"], sp)
                if cod in manual.get("repetidas", {}):
                    hechas, fallas = resolver_repetidas(c, manual["repetidas"][cod],
                                                        manual.get("total_con_error", {}).get(cod, {}).get(a))
                    for i, (concepto, prueba) in hechas.items():
                        m[i].pop("repetida", None)
                        if concepto is None:
                            m[i]["omitir"] = prueba
                        else:
                            m[i].update({"id": id_indicador(cod, concepto), "concepto": concepto, "comprobado": prueba})
                    if fallas:
                        e.setdefault("mapeo_manual_fallas", {})[a] = fallas
                if (ren := manual.get("renombres", {}).get(cod, {}).get(a)):
                    por_col = {x["col"]: k for k, x in enumerate(m)}
                    for col, concepto in ren["columnas"].items():
                        m[por_col[col]].pop("repetida", None)
                        m[por_col[col]].update({"id": id_indicador(cod, concepto), "concepto": concepto,
                                                "comprobado": "renombre a mano: " + " ".join(ren["motivo"].split())})
                    # lo que queda repetido después del renombre: si su ruta ya es única, deja de estar repetida
                    otras = [x for x in m if "concepto" not in x]
                    for x in otras:
                        if x.get("repetida") and sum(slug(y["ruta"]) == slug(x["ruta"]) for y in otras) == 1:
                            x.pop("repetida")
                            x["comprobado"] = "ruta única después del renombre de " + ", ".join(ren["columnas"])
                    renombradas = set(ren["columnas"]) | {x["col"] for x in otras if "comprobado" in x}
                    quedan = [f for f in e.get("mapeo_manual_fallas", {}).get(a, []) if f.split(" ", 1)[0] not in renombradas]
                    if quedan:
                        e["mapeo_manual_fallas"][a] = quedan
                    else:
                        e.get("mapeo_manual_fallas", {}).pop(a, None)
                for ruta, regla_c in manual.get("conceptos", {}).get(cod, {}).items():
                    if ruta not in c["rutas"]:
                        continue
                    i = c["rutas"].index(ruta)
                    t = c["rutas"].index(regla_c["total"]) if regla_c.get("total") else i
                    cols = [j for j, r in enumerate(c["rutas"]) if j != t and any(
                        r == x or (x.endswith("/") and r.startswith(x)) or (x.startswith("*/") and r.endswith(x[1:]))
                        for x in regla_c["suma"])]
                    explicada = (regla_c.get("diferencia_explicada") or {}).get(a)
                    if cols and (explicada or _igual(c["valores"][t], _suma(c["valores"], cols))):
                        prueba = f"{c['columnas'][t]} = " + " + ".join(c["columnas"][j] for j in cols)
                        if explicada:
                            suma = _suma(c["valores"], cols)
                            difs = [f"{c['rotulos'][f]} {x}≠{y}" for f, (x, y) in enumerate(zip(c["valores"][t], suma)) if x is not None and x != y]
                            prueba += f"; no cierra en {len(difs)} filas ({', '.join(difs[:3])}): {explicada}"
                        m[i].update({"id": id_indicador(cod, regla_c["concepto"]), "concepto": regla_c["concepto"],
                                     "comprobado": prueba})
                    else:
                        e.setdefault("mapeo_manual_fallas", {}).setdefault(a, []).append(
                            f"{c['columnas'][i]} «{ruta}»: la suma de «{regla_c['suma']}» no da {c['columnas'][t]}")
                if (regla := manual.get("anio_real", {}).get(cod, {}).get(a)):
                    cambios, notas = anio_real(ex, cod, a, regla)
                    for i, cambio in cambios.items():
                        m[i].update(cambio)
                    if notas:
                        e.setdefault("anio_real_notas", {})[a] = notas
                ids = [x["id"] for x in m]
                if len(set(ids)) != len(ids):
                    raise SystemExit(f"{cod} {a}: ids repetidos después del mapeo a mano")
                e["mapeo"][a] = m
        cuadros[cod] = e
    conceptos_2024(cuadros, manual)
    reg = {
        "id": "mec_anuario_educacion",
        "nombre": "Anuario Estadístico de Educación (MEC)",
        "organismo": "Ministerio de Educación y Cultura (MEC)",
        "pagina": PAGINA,
        "url_descarga": archivos[ANIOS[-1]]["url"],
        "formato": ("Una planilla xlsx por año lectivo (2020–2024; 2015–2019 en .rar, F4.9). Más de 100 hojas: presentación, "
                    "serie «MATRÍCULA DEL SISTEMA 2002-<año>», una hoja separadora (índice) por nivel, hojas CONTROL y un cuadro por "
                    "hoja (II-<nivel>.<tema>.<n>). Cada cuadro: título con el año, 2–4 filas de encabezado con celdas combinadas, "
                    "filas y pie con «Fuente:» y «Nota:». Muchas celdas son fórmulas con su valor calculado guardado."),
        "licencia": "No publicada por el MEC en la página del anuario. Se cita la fuente según cada cuadro.",
        "cita": "Fuente: MEC, Anuario Estadístico de Educación <año> (pie de cada cuadro).",
        "frecuencia": "anual (un anuario por año lectivo, publicado al año siguiente o el otro)",
        "estado": "en preparación",
        "cargar": True,
        "script": "pipeline/mec_anuario_cargar.py",
        "carpeta_original": "mec_anuario",
        "temas": ["Educación"],
        "niveles_publicados": ["pais", "region", "departamento"],
        "nivel_mas_detallado": "departamento",
        "notas": ["Solo sitios oficiales del MEC (gub.uy). El Anuario Estadístico Nacional del INE (cap. 3.1) se usa solo como control.",
                  "Los cuadros de matrícula y egresos son de estudiantes; los de rendimiento cuentan resultados de fin de año, no la matrícula inicial."],
        "notas_internas": ["Inventario y mapeo generados por scripts/inventario_mec.py (F4.1, #164); revisar los tipos automáticos.",
                           "`cargar: true` desde F4.4 (#167): captura con pipeline/mec_anuario_captura.py, carga con pipeline/mec_anuario_cargar.py.",
                           "D4: `datos_de_otro_anio` se carga con el año real que dice el pie; si el anuario de ese año ya lo publica, gana el suyo.",
                           "D5: las columnas `repetida` y los totales mal etiquetados por `completar_grupos` se mapean a mano en F4.3.",
                           "D6: los conceptos siguen la vista de cuadros del último anuario (2024); los años anteriores se mapean a esos conceptos donde significan lo mismo.",
                           "RESTO DEL PAÍS = TOTAL − MONTEVIDEO (confirmado por el mantenedor); el control AC-E18 sigue."],
        "anuarios": {a: {k: archivos[a][k] for k in ("pagina", "url", "http", "sha256", "bytes", "publicado", "actualizado", "revisado")} for a in ANIOS},
        "serie_nacional": {"hoja": "MATRÍCULA DEL SISTEMA 2002-<año>", "tipo": "B", "ola": 1, "unidad": "estudiantes",
                           "nota": "Se lee del anuario más reciente (F4.3, parsear_serie_matricula); el mapeo va en F4.3."},
        "cuadros": cuadros,
    }
    encabezado = ("# Registro de fuente (AC-P9, AC-E1, AC-E2). Generado por scripts/inventario_mec.py (F4.1, #164);\n"
                  "# regenerar en lugar de editar a mano. Inventario: docs/investigacion/mec_anuario_inventario.md\n")
    (RAIZ / "fuentes" / "mec_anuario_educacion.yml").write_text(
        encabezado + yaml.safe_dump(reg, allow_unicode=True, sort_keys=False, width=160), encoding="utf-8")
    return cuadros


if __name__ == "__main__":
    sys.exit(main())
