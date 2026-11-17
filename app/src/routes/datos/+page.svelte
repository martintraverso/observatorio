<script lang="ts">
	import { fecha } from '#lib/formato.ts';
	import { NOMBRE_SITIO, URL_REPOSITORIO, urlDescarga } from '#lib/sitio.ts';

	let { data } = $props();

	// Archivos de cada release de datos (scripts/publicar.py).
	const DESCARGAS = [
		{ archivo: 'observaciones.parquet', que: 'Todos los valores: indicador, territorio, período, valor y captura de origen.' },
		{ archivo: 'territorios.parquet', que: 'Todos los territorios con su geometría completa (GeoParquet).' },
		{ archivo: 'observatorio.duckdb', que: 'Todo junto en una base DuckDB. Empezá por la vista v_observaciones.' },
		{ archivo: 'web.zip', que: 'Geometrías simplificadas (GeoJSON y PMTiles), índice y fichas en JSON.' },
		{ archivo: 'reporte_validacion.md', que: 'Controles de calidad de la última corrida.' }
	];
</script>

<svelte:head>
	<title>Datos · {NOMBRE_SITIO}</title>
</svelte:head>

<h1>Datos</h1>
<p>
	Todo lo que muestra el sitio se puede descargar. Los archivos se generan automáticamente a partir de los
	originales de cada fuente; esta versión es del {fecha(data.manifest.generado)}.
</p>

<ul class="descargas">
	{#each DESCARGAS as d (d.archivo)}
		<li class="tarjeta">
			<a href={urlDescarga(d.archivo)}><code>{d.archivo}</code></a>
			<p>{d.que}</p>
		</li>
	{/each}
</ul>

<p>
	Versiones anteriores y tablas sueltas: <a href="{URL_REPOSITORIO}/releases">releases del repositorio</a>.
</p>

<h2>Licencia y cita</h2>
<p>
	Datos del Instituto Nacional de Estadística (INE), Unidades geoestadísticas Censo 2023. «El uso es libre,
	citando como fuente al INE.» Al usar estos archivos, citá al INE y a Observatorio Uruguay.
</p>

<style>
	.descargas {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: var(--espacio-4);
		list-style: none;
		padding: 0;
	}

	.descargas a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
		font-weight: 600;
	}

	.descargas p {
		margin: 0;
	}
</style>
