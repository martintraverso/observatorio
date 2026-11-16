"""Huellas (sha256) de los originales."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_archivo(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def sha256_carpeta(carpeta: Path, archivos: list[str]) -> str:
    """Huella de una carpeta: sha256 de los sha256 de `archivos`, en orden alfabético."""
    h = hashlib.sha256()
    for nombre in sorted(archivos):
        h.update(sha256_archivo(carpeta / nombre).encode())
    return h.hexdigest()


def huella_entrada(entrada: Path, archivos: list[str]) -> tuple[str, str]:
    """(sha256, nombre) del original: un zip o una carpeta con `archivos`."""
    if entrada.is_file():
        return sha256_archivo(entrada), entrada.name
    if entrada.is_dir():
        return sha256_carpeta(entrada, archivos), entrada.name
    raise FileNotFoundError(f"No encuentro {entrada}")
