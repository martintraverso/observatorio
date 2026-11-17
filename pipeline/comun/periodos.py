"""Períodos de las observaciones (F2.2, SYSTEM.md §5).

Cada observación tiene `periodo` (etiqueta para mostrar), `periodo_inicio` y `periodo_fin` (fechas) y
`tipo_periodo`. Las encuestas refieren a trimestres móviles, no a años: un informe de setiembre de 2026
es el trimestre julio–setiembre (AC-L10).
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import NamedTuple

TIPOS_PERIODO = ("censo", "mes", "trimestre_movil", "trimestre", "semestre", "anio")
COLUMNAS_PERIODO = ["periodo", "periodo_inicio", "periodo_fin", "tipo_periodo"]


class Periodo(NamedTuple):
    etiqueta: str
    inicio: dt.date
    fin: dt.date
    tipo: str

    def columnas(self) -> dict:
        """Las columnas de `observaciones` para este período."""
        return {"periodo": self.etiqueta, "periodo_inicio": self.inicio, "periodo_fin": self.fin,
                "tipo_periodo": self.tipo}


def _ultimo_dia(anio: int, mes: int) -> dt.date:
    return dt.date(anio, mes, calendar.monthrange(anio, mes)[1])


def censo(anio: int) -> Periodo:
    """Censo: una fecha de referencia convencional (1 de enero del año), etiqueta = el año."""
    d = dt.date(anio, 1, 1)
    return Periodo(str(anio), d, d, "censo")


def trimestre_movil(anio_fin: int, mes_fin: int) -> Periodo:
    """Los tres meses que terminan en `mes_fin` de `anio_fin`: (2026, 9) -> 2026-07-01 … 2026-09-30."""
    if not 1 <= mes_fin <= 12:
        raise ValueError(f"Mes inválido: {mes_fin}")
    anio_ini, mes_ini = (anio_fin, mes_fin - 2) if mes_fin > 2 else (anio_fin - 1, mes_fin + 10)
    inicio = dt.date(anio_ini, mes_ini, 1)
    return Periodo(f"{anio_ini}-{mes_ini:02d}/{anio_fin}-{mes_fin:02d}", inicio, _ultimo_dia(anio_fin, mes_fin),
                   "trimestre_movil")
