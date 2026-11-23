"""Lectura mínima de planillas xlsx con la biblioteca estándar (F3.3).

Solo lo que necesitan las series del INE (la primera hoja de `xl/workbook.xml`) y los anuarios del MEC (una hoja
por nombre, con sus celdas combinadas, F4.3a): los textos compartidos resueltos y, en las celdas con fórmula, el
valor calculado que guardó la planilla. No evalúa fórmulas ni lee estilos. Una celda sin referencia (`r`) hace
fallar la lectura: no se descarta nada en silencio.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_M = f"{{{NS['m']}}}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"


def _hojas(z: zipfile.ZipFile) -> dict[str, str]:
    """{nombre: ruta en el zip} de las hojas del libro, en orden, según workbook.xml y sus relaciones."""
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).iter(_REL)}
    hojas = {}
    for hoja in ET.fromstring(z.read("xl/workbook.xml")).findall("m:sheets/m:sheet", NS):
        destino = rels.get(hoja.get(_R))
        if not destino:
            raise ValueError(f"No encuentro el archivo de la hoja {hoja.get('name')!r}")
        hojas[hoja.get("name")] = destino.lstrip("/") if destino.startswith("/") else f"xl/{destino}"
    return hojas


def _primera_hoja(z: zipfile.ZipFile) -> str:
    """Ruta en el zip de la primera hoja del libro."""
    hojas = _hojas(z)
    if not hojas:
        raise ValueError("La planilla no tiene hojas")
    return next(iter(hojas.values()))


def nombres_de_hojas(xlsx: bytes) -> list[str]:
    """Nombres de las hojas, en el orden del libro (con sus espacios, tal cual)."""
    with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
        return list(_hojas(z))


def _texto(si) -> str:
    """Texto de un <si>: sus <t> directos o los de sus tramos <r>, sin la fonética (<rPh>)."""
    return "".join(t.text or "" for t in [*si.findall("m:t", NS), *si.findall("m:r/m:t", NS)])


def _columna(letras: str) -> int:
    n = 0
    for ch in letras:
        n = n * 26 + ord(ch) - 64
    return n


def leer_primera_hoja(xlsx: bytes) -> dict[int, dict[int, str | float]]:
    """{fila: {columna: valor}} de la primera hoja (filas y columnas desde 1). Los textos quedan como str y los
    números como float con la precisión guardada; las celdas vacías no aparecen."""
    with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
        return _leer(z, _primera_hoja(z))[0]


def leer_hoja(xlsx: bytes, nombre: str) -> tuple[dict[int, dict[int, str | float]], list[tuple[int, int, int, int]]]:
    """Celdas ({fila: {columna: valor}}, como `leer_primera_hoja`) y celdas combinadas
    ([(fila_ini, col_ini, fila_fin, col_fin)], en el orden del archivo) de la hoja `nombre`."""
    with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
        hojas = _hojas(z)
        if nombre not in hojas:
            raise ValueError(f"La planilla no tiene la hoja {nombre!r}")
        return _leer(z, hojas[nombre])


def _celda(ref: str) -> tuple[int, int]:
    m = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", ref)
    if not m:
        raise ValueError(f"Referencia de celda inválida: {ref!r}")
    return int(m.group(2)), _columna(m.group(1))


def _leer(z: zipfile.ZipFile, hoja: str):
    nombres = z.namelist()
    textos = []
    if "xl/sharedStrings.xml" in nombres:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            textos.append(_texto(si))
    if hoja not in nombres:
        raise ValueError(f"La planilla no tiene {hoja}")
    raiz = ET.fromstring(z.read(hoja))
    combinadas = []
    for mc in raiz.iter(f"{_M}mergeCell"):
        ini, _, fin = mc.get("ref", "").partition(":")
        (f1, c1), (f2, c2) = _celda(ini), _celda(fin or ini)
        combinadas.append((f1, c1, f2, c2))
    filas: dict[int, dict[int, str | float]] = {}
    for c in raiz.iter(f"{_M}c"):
        m = re.fullmatch(r"([A-Z]+)(\d+)", c.get("r", ""))
        v = c.find("m:v", NS)
        tipo = c.get("t")
        if not m:
            raise ValueError(f"Celda sin referencia válida en la hoja ({c.get('r')!r})")
        if tipo == "inlineStr":
            valor: str | float | None = "".join(t.text or "" for t in c.iter(f"{_M}t"))
        elif v is None or v.text is None:
            continue
        elif tipo == "s":
            valor = textos[int(v.text)]
        elif tipo in ("str", "e"):
            valor = v.text
        else:
            valor = float(v.text)
        if valor == "":
            continue
        filas.setdefault(int(m.group(2)), {})[_columna(m.group(1))] = valor
    return filas, combinadas
