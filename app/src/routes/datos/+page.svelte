<script lang="ts">
	// Descargas (M8, AC-D1, AC-D2): cada archivo con tamaño, fecha, licencia y cómo citar.
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import { resolve } from '$app/paths';
	import { etiquetaNivel, NIVELES } from '#lib/datos.ts';
	import { fecha, tamano } from '#lib/formato.ts';
	import { NOMBRE_SITIO, URL_REPOSITORIO, urlDescarga } from '#lib/sitio.ts';

	let { data } = $props();

	const GRUPOS = ['Observaciones', 'Territorios', 'Base completa'];
	let grupos = $derived(
		GRUPOS.map((g) => [g, data.archivos.filter((a) => a.grupo === g)] as const).filter(([, l]) => l.length)
	);
	// AC-V30: territorios agrupados por nivel (nombre legible), una columna por formato
	const FORMATOS = ['parquet', 'geojson'];
	let territorios = $derived.by(() => {
		const porNivel = new Map<string, Record<string, (typeof data.archivos)[number]>>();
		for (const a of data.archivos.filter((x) => x.grupo === 'Territorios')) {
			const m = /^territorios_(.+)\.(\w+)$/.exec(a.nombre);
			if (!m) continue;
			porNivel.set(m[1], { ...porNivel.get(m[1]), [m[2]]: a });
		}
		const orden = (n: string) => (NIVELES as string[]).indexOf(n) + 1 || 99;
		return [...porNivel].sort(([a], [b]) => orden(a) - orden(b));
	});
	// los demás archivos del grupo (todos los niveles juntos, correspondencias), en filas aparte
	let otrosTerritorios = $derived(data.archivos.filter((a) => a.grupo === 'Territorios' && !/^territorios_.+\.\w+$/.test(a.nombre)));
	const NOMBRE_OTRO: Record<string, string> = {
		'territorios.parquet': 'Todos los niveles',
		'correspondencias.parquet': 'Correspondencias entre niveles'
	};
	let fuentesNombradas = $derived(data.fuentes.map((f) => `${f.organismo.replace(/^.*\((\w+)\)$/, '$1')}, ${f.nombre}`).join('; '));
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
	<h2>Licencias y cómo citar</h2>
	<ul>
		{#each data.fuentes as f (f.id)}
			<li><a href={resolve('/fuentes/[id]', { id: f.id })}>{f.nombre}</a> ({f.organismo}): «{f.licencia}»</li>
		{/each}
	</ul>
	<p>Cita sugerida: Observatorio Uruguay, a partir de {fuentesNombradas}. Indicar el archivo y la fecha de descarga.</p>
</div>


{#each grupos as [grupo, lista] (grupo)}
	{#if grupo === 'Territorios'}
		<section aria-labelledby="g-territorios">
			<h2 id="g-territorios">Territorios</h2>
			<p class="suave">Geometrías de cada nivel: completas (GeoParquet, EPSG:4326) y simplificadas (GeoJSON).</p>
			<TablaDesplazable etiqueta="Territorios" clase="tarjeta">
				<table>
					<caption class="visualmente-oculto">Territorios: archivos para descargar, por nivel</caption>
					<thead>
						<tr>
							<th scope="col">Nivel</th>
							<th scope="col">GeoParquet (completa)</th>
							<th scope="col">GeoJSON (simplificada)</th>
							<th scope="col">Generado</th>
						</tr>
					</thead>
					<tbody>
						{#each territorios as [nivel, archivos] (nivel)}
							<tr>
								<th scope="row">{etiquetaNivel(nivel)}</th>
								{#each FORMATOS as formato (formato)}
									{@const a = archivos[formato]}
									<td>
										{#if a}
											<a href={urlDescarga(a.nombre)} download><code>{a.nombre}</code></a>
											<span class="suave tamano">{tamano(a.bytes)}</span>
										{:else}—{/if}
									</td>
								{/each}
								<td>{fecha(data.generado)}</td>
							</tr>
						{/each}
					{#each otrosTerritorios as a (a.nombre)}
						<tr>
							<th scope="row">{NOMBRE_OTRO[a.nombre] ?? a.descripcion}</th>
							<td>
								<a href={urlDescarga(a.nombre)} download><code>{a.nombre}</code></a>
								<span class="suave tamano">{tamano(a.bytes)}</span>
							</td>
							<td>—</td>
							<td>{fecha(data.generado)}</td>
						</tr>
					{/each}
					</tbody>
				</table>
			</TablaDesplazable>
		</section>
	{:else}
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
	{/if}
{/each}

<p class="suave">
	Cada archivo se puede verificar con su sha256 (en <code>manifest.json</code> y en las notas de cada publicación).
	Versiones anteriores: <a href="{URL_REPOSITORIO}/releases">publicaciones del repositorio</a>. Los archivos
	originales, sin procesar, están en la publicación
	<a href="{URL_REPOSITORIO}/releases/tag/crudos">crudos</a>.
</p>

<style>
	.licencia ul {
		margin: 0 0 var(--espacio-2);
		padding-left: var(--espacio-4);
	}

	.tamano {
		display: block;
		font-size: var(--texto-xs);
	}

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
