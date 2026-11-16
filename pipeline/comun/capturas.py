"""Capturas: de qué archivo salió cada dato, y el historial de corridas.

`capturas.parquet` tiene las capturas referidas por las observaciones actuales.
`capturas_historial.parquet` es append-only: una fila por corrida y fuente, con
el resultado (`nuevo`, `reprocesado`, `sin cambios` o `error`). En GitHub Actions
se baja del release `datos` al empezar y se vuelve a publicar al terminar.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

ARCHIVO_HISTORIAL = "capturas_historial.parquet"
RESULTADOS = ("nuevo", "reprocesado", "sin cambios", "error")
PROCESADOS = ("nuevo", "reprocesado")  # corridas que dejaron salidas válidas
COLUMNAS = ["id", "fuente_id", "archivo", "sha256", "fecha_proceso", "resultado", "detalle"]


def ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def captura_id(fuente_id: str, sha256: str) -> str:
    return f"{fuente_id}:{sha256[:12]}"


def nueva_captura(fuente_id: str, archivo: str, sha256: str, fecha_proceso: str) -> dict:
    if not sha256 or not archivo:
        raise ValueError("Una captura necesita archivo y sha256")
    return {"id": captura_id(fuente_id, sha256), "fuente_id": fuente_id, "archivo": archivo,
            "sha256": sha256, "fecha_proceso": fecha_proceso}


class Historial:
    """Historial append-only de capturas, guardado en `<salida>/capturas_historial.parquet`."""

    def __init__(self, salida: Path):
        self.path = Path(salida) / ARCHIVO_HISTORIAL

    def leer(self) -> pd.DataFrame:
        if self.path.exists():
            return pd.read_parquet(self.path)
        return pd.DataFrame({c: pd.Series(dtype="string") for c in COLUMNAS})

    def ultima_procesada(self, fuente_id: str) -> dict | None:
        """Última corrida de la fuente que dejó salidas válidas (nuevo o reprocesado)."""
        h = self.leer()
        h = h[(h.fuente_id == fuente_id) & h.resultado.isin(PROCESADOS)]
        return None if h.empty else h.iloc[-1].to_dict()

    def agregar(self, captura: dict, resultado: str, detalle: str = "") -> None:
        if resultado not in RESULTADOS:
            raise ValueError(f"Resultado desconocido: {resultado}")
        fila = pd.DataFrame([{**{c: captura[c] for c in COLUMNAS[:5]}, "resultado": resultado,
                              "detalle": detalle}], dtype="string")
        previo = self.leer()
        todo = fila if previo.empty else pd.concat([previo.astype("string"), fila], ignore_index=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        todo.to_parquet(tmp, index=False)
        tmp.replace(self.path)
