# Observatorio Uruguay

Reúne datos públicos sobre el territorio uruguayo, los guarda en una base propia y los vincula a un territorio (departamento, sección, segmento, localidad).

## Fase 0: territorios del Censo 2023

Carga las unidades geoestadísticas que publica el INE y sus conteos del Censo 2023 (personas, hombres, mujeres, viviendas).

| Nivel | Cantidad | Código INE |
|---|---:|---|
| Departamento | 19 | 2 caracteres (Montevideo = 01) |
| Sección censal | 236 | 4 (depto + sección) |
| Segmento censal | 4.538 | 7 (+ segmento) |
| Localidad censal | 652 | 5 (depto + localidad; 900 = rural) |
| Barrio (Montevideo) | 63 | código INE de barrio |
| CCZ (Montevideo) | 18 | número de CCZ |

El paquete del INE no incluye zonas censales: el nivel más fino es el segmento.

### Cómo correrlo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Bajar el zip de https://www.gub.uy/instituto-nacional-estadistica/politicas-y-gestion/unidades-geostadisticas
# y guardarlo en datos/crudo/
python pipeline/territorios_2023.py datos/crudo/Unidades_Geoestadisticas_Censo_2023.zip
pytest -q
```

Tarda unos 15 segundos. Los resultados quedan en `datos/salida/`:

| Archivo | Qué tiene |
|---|---|
| `observatorio.duckdb` | Todo junto. Empezá por la vista `v_observaciones`. |
| `territorios.parquet` | Un registro por territorio, con geometría completa (GeoParquet). |
| `observaciones.parquet` | Indicador, territorio, período, valor y captura de origen. |
| `correspondencias.parquet` | Relaciones entre territorios (segmento → localidad). |
| `web/*.geojson` | Geometrías simplificadas por nivel, para la app. |
| `reporte_validacion.md` | Controles de calidad. Revisalo después de cada corrida. |

Ejemplo de consulta:

```sql
-- duckdb datos/salida/observatorio.duckdb
SELECT territorio, nivel, valor
FROM v_observaciones
WHERE indicador = 'pob_total' AND depto = '16' AND nivel IN ('departamento', 'seccion')
ORDER BY nivel, codigo;
```

### Reglas que sigue la base

- **Cada dato se guarda en el nivel en que se publica.** La población de un departamento no es la suma de sus secciones: el INE ubica a parte de las personas (enumeración administrativa) solo a nivel de localidad o departamento. En 2023 la diferencia total es de 157.929 personas. Ver `reporte_validacion.md`.
- **Cada valor apunta al archivo del que salió** (`captura_id` → nombre del archivo, sha256 y fecha).
- **Las geometrías tienen versión** (`version_geo = INE-2023`). Cuando se carguen las de 2011, conviven con estas.
- El polígono "LIMITE CONTESTADO" del INE se guarda como `area_especial` y no lleva conteos propios.

### Automatización

`.github/workflows/fase0.yml` corre el pipeline a mano o cada lunes, prueba el resultado y publica los archivos en el release `datos` del repositorio. Como la descarga del INE falla a veces, conviene subir el zip original como asset de un release llamado `crudos`.

## Fuente y licencia de los datos

Instituto Nacional de Estadística (INE), Unidades geoestadísticas Censo 2023. Según sus metadatos: *"El uso es libre, citando como fuente al INE."* Contacto de cartografía: cartogra@ine.gub.uy.
