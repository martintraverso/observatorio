"""Código compartido por los scripts del pipeline (una fuente por script).

  huella      sha256 de archivos y carpetas
  entrada     abrir el original (zip o carpeta) de forma segura
  capturas    registro de capturas e historial append-only (resultado: nuevo / sin cambios / ...)
  controles   controles de calidad, tabla para el reporte y código de salida
  registro    carga y valida el registro de fuentes (fuentes/*.yml)
  salida      escritura de Parquet y DuckDB
"""
