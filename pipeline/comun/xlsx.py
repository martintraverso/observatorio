"""Lectura mínima de planillas xlsx con la biblioteca estándar (F3.3).

Solo lo que necesitan las series del INE: la primera hoja, con los textos compartidos resueltos y, en las
celdas con fórmula, el valor calculado que guardó la planilla. No evalúa fórmulas ni lee estilos.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_M = f"{{{NS['m']}}}"


def _columna(letras: str) -> int:
    n = 0
    for ch in letras:
        n = n * 26 + ord(ch) - 64
    return n


def leer_primera_hoja(xlsx: bytes) -> dict[int, dict[int, str | float]]:
    """{fila: {columna: valor}} de la primera hoja (filas y columnas desde 1). Los textos quedan como str y los
    números como float con la precisión guardada; las celdas vacías no aparecen."""
    with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
        nombres = z.namelist()
        textos = []
        if "xl/sharedStrings.xml" in nombres:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                textos.append("".join(t.text or "" for t in si.iter(f"{_M}t")))
        hoja = "xl/worksheets/sheet1.xml"
        if hoja not in nombres:
            raise ValueError("La planilla no tiene xl/worksheets/sheet1.xml")
        filas: dict[int, dict[int, str | float]] = {}
        for c in ET.fromstring(z.read(hoja)).iter(f"{_M}c"):
            m = re.fullmatch(r"([A-Z]+)(\d+)", c.get("r", ""))
            v = c.find("m:v", NS)
            tipo = c.get("t")
            if not m:
                continue
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
    return filas
