"""Genera el fixture de tests a partir del zip original del INE.

Recorta el paquete "Unidades geoestadísticas Censo 2023" a un subconjunto chico
que se puede commitear (< 2 MB) y con el que el pipeline corre igual que con
el paquete completo:

  depto_23_pg        01 Montevideo, 02 Artigas (+ LIMITE CONTESTADO), 07 Flores, 16 San José
  sc_23_pg           secciones de Flores (07)
  sg_23_pg           segmentos de Flores
  loc_23_pg          localidades de Flores
  barrios_mvd_23_pg  todos los barrios de Montevideo
  ccz_mvd_23_pg      todos los CCZ de Montevideo

Los atributos (códigos, nombres, conteos, AREA_KM2) se copian sin cambios. Solo
las geometrías se simplifican (coverage_simplify, ~10 m) para bajar el tamaño.

Escribe:
  tests/fixtures/ine_2023_mini.zip   los 6 geopackages, con los mismos nombres de archivo y capa
  tests/fixtures/esperado.yml        valores esperados del recorte (para --esperado y los tests)

Uso:
  python scripts/crear_fixture.py datos/crudo/Unidades_Geoestadisticas_Censo_2023.zip [--salida tests/fixtures]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pyogrio
import shapely
import yaml

DEPTOS = ["01", "02", "07", "16"]
DEPTO_JERARQUIA = "07"  # departamento con secciones, segmentos y localidades completas
TOLERANCIA = 1e-4  # grados (~10 m)
FECHA_ZIP = (2023, 1, 1, 0, 0, 0)  # fija, para que el zip no cambie solo por la fecha

FILTROS = {
    "depto_23_pg": lambda g: g.DEPTO.isin(DEPTOS),
    "sc_23_pg": lambda g: g.DEPTO == DEPTO_JERARQUIA,
    "sg_23_pg": lambda g: g.DEPTO == DEPTO_JERARQUIA,
    "loc_23_pg": lambda g: g.DEPTO == DEPTO_JERARQUIA,
    "barrios_mvd_23_pg": lambda g: g.index == g.index,
    "ccz_mvd_23_pg": lambda g: g.index == g.index,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def extraer(zip_path: Path, tmp: Path) -> Path:
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            if not str((tmp / m.filename).resolve()).startswith(str(tmp.resolve())):
                raise ValueError(f"Ruta insegura dentro del zip: {m.filename}")
        z.extractall(tmp)
    carpeta = next((p.parent for p in tmp.rglob("depto_23_pg.gpkg")), None)
    if carpeta is None:
        raise FileNotFoundError("El zip no contiene depto_23_pg.gpkg")
    return carpeta


def recortar(carpeta: Path, destino: Path) -> dict[str, gpd.GeoDataFrame]:
    capas = {}
    for archivo, filtro in FILTROS.items():
        origen = carpeta / f"{archivo}.gpkg"
        capa = pyogrio.list_layers(origen)[0][0]
        g = gpd.read_file(origen, layer=capa)
        g = g[filtro(g)].copy()
        g["geometry"] = shapely.coverage_simplify(g.geometry.values, TOLERANCIA)
        g.to_file(destino / f"{archivo}.gpkg", driver="GPKG", layer=capa)
        capas[archivo] = g
    return capas


def calcular_esperado(capas: dict[str, gpd.GeoDataFrame]) -> dict:
    d = capas["depto_23_pg"]
    lc = d.NOMDEPTO == "LIMITE CONTESTADO"
    sc = capas["sc_23_pg"]
    return {
        "territorios_por_nivel": {
            "departamento": int((~lc).sum()),
            "seccion": len(sc),
            "segmento": len(capas["sg_23_pg"]),
            "localidad": len(capas["loc_23_pg"]),
            "barrio_mvd": len(capas["barrios_mvd_23_pg"]),
            "ccz_mvd": len(capas["ccz_mvd_23_pg"]),
            "area_especial": int(lc.sum()),
            # Niveles derivados por el pipeline (F2.3): país y municipios de Montevideo.
            "pais": int((~lc).any()),
            "municipio_mvd": int(capas["ccz_mvd_23_pg"].NOMMUNICIPIO.nunique()),
        },
        "departamentos_con_secciones": int(sc.DEPTO.nunique()),
        "pob_total_departamentos": int(d[~lc].POB_TOT_23.sum()),
        "pob_total_secciones": int(sc.POB_TOT_23.sum()),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("original", type=Path, help="zip original del INE")
    ap.add_argument("--salida", type=Path, default=Path("tests/fixtures"))
    args = ap.parse_args(argv)
    args.salida.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "original").mkdir()
        (tmp / "recorte").mkdir()
        capas = recortar(extraer(args.original, tmp / "original"), tmp / "recorte")

        zip_salida = args.salida / "ine_2023_mini.zip"
        with zipfile.ZipFile(zip_salida, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for archivo in sorted(FILTROS):
                info = zipfile.ZipInfo(f"{archivo}.gpkg", date_time=FECHA_ZIP)
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, (tmp / "recorte" / f"{archivo}.gpkg").read_bytes())

    esperado = calcular_esperado(capas)
    encabezado = (
        "# Valores esperados del fixture tests/fixtures/ine_2023_mini.zip.\n"
        "# Generado por scripts/crear_fixture.py; no editar a mano.\n"
        f"# Original: {args.original.name} · sha256 {sha256(args.original)}\n"
        f"# Recorte: departamentos {', '.join(DEPTOS)}; jerarquía completa de {DEPTO_JERARQUIA}; "
        f"barrios y CCZ de Montevideo; geometrías simplificadas a {TOLERANCIA}°.\n"
    )
    (args.salida / "esperado.yml").write_text(
        encabezado + yaml.safe_dump(esperado, sort_keys=False, allow_unicode=True), encoding="utf-8")

    tamano = zip_salida.stat().st_size
    print(f"{zip_salida}: {tamano / 1e6:.2f} MB")
    if tamano > 2_000_000:
        print("El fixture supera 2 MB", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
