"""Registro de fuentes: un fuentes/<id>.yml por dataset (AC-P9)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

CAMPOS_OBLIGATORIOS = ["id", "nombre", "organismo", "pagina", "url_descarga", "formato", "licencia",
                       "frecuencia", "estado", "temas", "nivel_mas_detallado", "niveles_publicados", "notas"]
ESTADOS = ("activa", "en preparación", "a relevar")
# Las fuentes activas además dicen cómo se consiguen y procesan.
CAMPOS_ACTIVA = ["archivo_original", "script"]
COLUMNAS = [*CAMPOS_OBLIGATORIOS[:9], "contacto", "version_geo", *CAMPOS_OBLIGATORIOS[9:], *CAMPOS_ACTIVA]
RAIZ = Path(__file__).resolve().parents[2]


def validar_fuente(f: dict, archivo: str) -> list[str]:
    errores = [f"{archivo}: falta '{c}'" for c in CAMPOS_OBLIGATORIOS if f.get(c) in (None, "", [])]
    if f.get("estado") not in ESTADOS:
        errores.append(f"{archivo}: estado '{f.get('estado')}' no es uno de {ESTADOS}")
    for c in ("temas", "niveles_publicados", "notas"):
        if c in f and not isinstance(f[c], list):
            errores.append(f"{archivo}: '{c}' debe ser una lista")
    if f.get("nivel_mas_detallado") not in (f.get("niveles_publicados") or []):
        errores.append(f"{archivo}: nivel_mas_detallado no está en niveles_publicados")
    if f.get("capas") and not f.get("version_geo"):
        errores.append(f"{archivo}: fuente geográfica sin version_geo")
    if f.get("estado") == "activa":
        errores += [f"{archivo}: una fuente activa necesita '{c}'" for c in CAMPOS_ACTIVA
                    if not f.get(c) and not (c == "archivo_original" and f.get("carpeta_original"))]
        if f.get("script") and not (RAIZ / f["script"]).is_file():
            errores.append(f"{archivo}: no existe el script {f['script']}")
        if f.get("archivo_original") and Path(f["archivo_original"]).name != f["archivo_original"]:
            errores.append(f"{archivo}: archivo_original debe ser un nombre de archivo, sin carpetas")
    if f.get("id") and Path(archivo).stem != f["id"]:
        errores.append(f"{archivo}: el nombre del archivo debe ser <id>.yml")
    return errores


def cargar_fuentes(carpeta: Path) -> dict[str, dict]:
    """Lee todos los fuentes/*.yml; falla si alguno no cumple el formato."""
    fuentes, errores = {}, []
    for path in sorted(Path(carpeta).glob("*.yml")):
        f = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        errores += validar_fuente(f, path.name)
        if f.get("id") in fuentes:
            errores.append(f"{path.name}: id repetido '{f['id']}'")
        fuentes[f.get("id")] = f
    if not fuentes:
        errores.append(f"No hay archivos .yml en {carpeta}")
    if errores:
        raise ValueError("Registro de fuentes inválido:\n  " + "\n  ".join(errores))
    return fuentes


def tabla_fuentes(fuentes: dict[str, dict]) -> pd.DataFrame:
    """Tabla `fuentes`: una fila por registro, con las columnas de COLUMNAS."""
    return pd.DataFrame([{c: f.get(c) for c in COLUMNAS} for f in fuentes.values()], columns=COLUMNAS)


def activas(fuentes: dict[str, dict]) -> list[dict]:
    """Fuentes con estado 'activa', en orden de id."""
    return [fuentes[k] for k in sorted(fuentes) if fuentes[k].get("estado") == "activa"]
