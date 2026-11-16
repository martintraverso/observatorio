"""Controles de calidad: se acumulan, van al reporte y deciden el código de salida."""

from __future__ import annotations

import sys


class Controles:
    def __init__(self):
        self.lista: list[dict] = []

    def chk(self, nombre: str, ok, detalle: str = "") -> None:
        self.lista.append({"control": nombre, "ok": bool(ok), "detalle": str(detalle)})

    @property
    def fallas(self) -> list[dict]:
        return [c for c in self.lista if not c["ok"]]

    def tabla_md(self) -> list[str]:
        return ["| Control | Resultado | Detalle |", "|---|---|---|",
                *[f"| {c['control']} | {'OK' if c['ok'] else 'FALLA'} | {c['detalle']} |" for c in self.lista]]

    def informar(self, err=None) -> int:
        """Lista las fallas en stderr y devuelve el código de salida (0 si no hay fallas)."""
        err = err or sys.stderr
        for c in self.fallas:
            print(f"FALLA: {c['control']} — {c['detalle']}", file=err)
        return 1 if self.fallas else 0
