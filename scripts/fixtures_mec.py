"""F4.1 (#164): recorta los anuarios del MEC 2024 y 2023 a los fixtures de `tests/fixtures/mec_anuario/`.

Conserva, por año, la serie nacional, los cuadros de la ola 1 (registro `fuentes/mec_anuario_educacion.yml`), cuadros
de tipo B y C de la ola 2 y los casos raros del inventario. Las hojas quedan con su formato, celdas combinadas y pies;
las fórmulas se guardan con su valor (openpyxl no conserva a la vez la fórmula y el valor calculado). Necesita
`openpyxl` (no es dependencia del proyecto).

Uso: python scripts/fixtures_mec.py [--dir datos/crudo/mec_anuario]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "tests" / "fixtures" / "mec_anuario"
SERIE = "MATRÍCULA DEL SISTEMA"
EXTRA = {
    "II-7.2.8": "tipo C: por institución universitaria; la hoja dice «Cuadro II-7.2.8» sin «Nº»",
    "II-8.1.7": "tipo C: por institución; código escrito «II- 8.1.7»",
    "II-5.1.1": "terciaria no universitaria: matrícula y docentes en el mismo cuadro",
    "II-2.3.2": "números guardados como texto; el título de 2024 no dice el año",
    "II-1.3.2": "en 2024 el pie dice que los datos son de 2022",
}
ANIOS = (2024, 2023)


def main(argv=None) -> int:
    import openpyxl  # herramienta de exploración: ver el docstring

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", type=Path, default=RAIZ / "datos" / "crudo" / "mec_anuario")
    args = ap.parse_args(argv)
    reg = yaml.safe_load((RAIZ / "fuentes" / "mec_anuario_educacion.yml").read_text(encoding="utf-8"))
    ola1 = {c for c, e in reg["cuadros"].items() if e["ola"] == 1}
    SALIDA.mkdir(parents=True, exist_ok=True)
    for anio in ANIOS:
        origen = args.dir / f"{anio}.xlsx"
        if reg["anuarios"][anio]["sha256"] != __import__("hashlib").sha256(origen.read_bytes()).hexdigest():
            raise SystemExit(f"{origen}: el sha256 no es el del registro")
        wb = openpyxl.load_workbook(origen, data_only=True)
        quedan = []
        for ws in list(wb.worksheets):
            t = ws.title.strip()
            if t.startswith(SERIE) or t in ola1 or t in EXTRA:
                quedan.append(t)
            else:
                wb.remove(ws)
        wb.save(SALIDA / f"{anio}.xlsx")
        print(anio, len(quedan), "hojas", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
