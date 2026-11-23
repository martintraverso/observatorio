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
    deptos = sum(1 for x in pl if x in DEPTOS)
    tipo = ("A" if ("total" in pl or "total del pais" in pl) and "montevideo" in pl and deptos >= 15
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
    escribir_inventario(ex, archivos)
    escribir_registro(ex, archivos)
    return 0


def escribir_inventario(ex: dict, archivos: dict) -> None:
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
                motivo = ("sin datos numéricos" if c.get("sin_datos") else
                          f"el título dice {c['anio_titulo']} (AC-E10: debe ser el año del archivo)"
                          if c.get("anio_titulo") and c["anio_titulo"] != a else None)
                if motivo:  # AC-E2: lo que no se carga figura con su motivo
                    e["mapeo"][a] = None
                    e.setdefault("sin_cargar", {})[a] = motivo
                    continue
                sp = solo_publica(c)
                e["mapeo"][a] = mapear(cod, c["columnas"], c["rutas"], sp)
        cuadros[cod] = e
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
        "carpeta_original": "mec_anuario",
        "temas": ["Educación"],
        "niveles_publicados": ["pais", "departamento"],
        "nivel_mas_detallado": "departamento",
        "notas": ["Solo sitios oficiales del MEC (gub.uy). El Anuario Estadístico Nacional del INE (cap. 3.1) se usa solo como control.",
                  "Los cuadros de matrícula y egresos son de estudiantes; los de rendimiento cuentan resultados de fin de año, no la matrícula inicial."],
        "notas_internas": ["Inventario y mapeo generados por scripts/inventario_mec.py (F4.1, #164); revisar los tipos automáticos.",
                           "Sin `cargar: true` hasta F4.4 (#167): con cargar y sin script el registro no valida (como en F3.1 y F2.1).",
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


if __name__ == "__main__":
    sys.exit(main())
