#!/usr/bin/env bash
# Sube al release "crudos" los originales de una fuente con carpeta (por defecto datos/crudo/ech_mt/) y su
# registro de capturas. Nunca reemplaza nada: solo agrega lo que falta. Ver scripts/crudos_carpeta.py.
# Uso: scripts/subir_crudos.sh [carpeta] [crudo]
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/crudos_carpeta.py subir --carpeta "${1:-ech_mt}" --crudo "${2:-datos/crudo}"
