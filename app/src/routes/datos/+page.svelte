<script lang="ts">
	// Descargas (M8, AC-D1, AC-D2): cada archivo con tamaño, fecha, licencia y cómo citar.
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import { fecha, tamano } from '#lib/formato.ts';
	import { NOMBRE_SITIO, URL_REPOSITORIO, urlDescarga } from '#lib/sitio.ts';

	let { data } = $props();

	const GRUPOS = ['Observaciones', 'Territorios', 'Base completa'];
	let grupos = $derived(
		GRUPOS.map((g) => [g, data.archivos.filter((a) => a.grupo === g)] as const).filter(([, l]) => l.length)
	);
	const formato = (nombre: string) => nombre.split('.').at(-1)!.toUpperCase().replace('MD', 'Markdown');
</script>

<svelte:head>
	<title>Datos · {NOMBRE_SITIO}</title>
</svelte:head>

<h1>Datos</h1>
<p>
	Todo lo que muestra el sitio se puede descargar. Los archivos se generan automáticamente a partir de los
	originales de cada fuente. Esta versión es del <strong>{fecha(data.generado)}</strong>.
</p>

<div class="licencia tarjeta">
	<h2>Licencia y cómo citar</h2>
	<p>Licencia de la fuente: «{data.licencia}»</p>
	<p>Cita sugerida: {data.cita}</p>
</div>

{#each grupos as [grupo, lista] (grupo)}
	<section aria-labelledby="g-{grupo}">
		<h2 id="g-{grupo}">{grupo}</h2>
		<TablaDesplazable etiqueta={grupo} clase="tarjeta">
			<table>
				<caption class="visualmente-oculto">{grupo}: archivos para descargar</caption>
				<thead>
					<tr>
						<th scope="col">Archivo</th>
						<th scope="col">Qué tiene</th>
						<th scope="col">Formato</th>
						<th scope="col" class="num">Tamaño</th>
						<th scope="col">Generado</th>
					</tr>
				</thead>
				<tbody>
					{#each lista as a (a.nombre)}
						<tr>
							<td><a href={urlDescarga(a.nombre)} download><code>{a.nombre}</code></a></td>
							<td>{a.descripcion}</td>
							<td>{formato(a.nombre)}</td>
							<td class="num">{tamano(a.bytes)}</td>
							<td>{fecha(data.generado)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</TablaDesplazable>
	</section>
{/each}

<p class="suave">
	Cada archivo se puede verificar con su sha256 (en <code>manifest.json</code> y en las notas de cada publicación).
	Versiones anteriores: <a href="{URL_REPOSITORIO}/releases">publicaciones del repositorio</a>. Los archivos
	originales, sin procesar, están en la publicación
	<a href="{URL_REPOSITORIO}/releases/tag/crudos">crudos</a>.
</p>

<style>
	.licencia h2 {
		font-size: var(--texto-m);
		margin-bottom: var(--espacio-2);
	}

	.licencia p {
		margin: var(--espacio-1) 0;
	}

	section {
		margin-top: var(--espacio-5);
	}

	td a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
		font-weight: 600;
	}

	code {
		font-size: var(--texto-s);
	}
</style>
