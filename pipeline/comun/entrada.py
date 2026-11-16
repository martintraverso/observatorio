"""Abrir originales sin confiar en su contenido."""

from __future__ import annotations

import zipfile
from pathlib import Path


def extraer_zip(zip_path: Path, destino: Path) -> Path:
    """Extrae el zip en `destino`, rechazando rutas que salgan de esa carpeta."""
    base = destino.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            if not (base / m.filename).resolve().is_relative_to(base):
                raise ValueError(f"Ruta insegura dentro del zip: {m.filename}")
        z.extractall(destino)
    return destino


def carpeta_con(raiz: Path, archivo: str) -> Path:
    """Primera carpeta bajo `raiz` que contiene `archivo`."""
    carpeta = next((p.parent for p in sorted(raiz.rglob(archivo))), None)
    if carpeta is None:
        raise FileNotFoundError(f"No encuentro {archivo} en el original")
    return carpeta
