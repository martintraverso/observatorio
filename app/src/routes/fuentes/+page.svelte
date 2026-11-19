<script lang="ts">
	// Catálogo de fuentes (M8, AC-SRC1, AC-SRC2).
	import { resolve } from '$app/paths';
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import { etiquetaNivel, NIVELES } from '#lib/datos.ts';
	import { fecha, numero } from '#lib/formato.ts';
	import { ESTADOS, filtrar, SIN_FILTROS, type Filtros } from '#lib/fuentes.ts';
	import { NOMBRE_SITIO } from '#lib/sitio.ts';

	let { data } = $props();

	let filtros = $state<Filtros>({ ...SIN_FILTROS });
	let visibles = $derived(filtrar(data.fuentes, filtros));
	let r = $derived(data.resumen);
	let organismos = $derived([...new Set(data.fuentes.map((f) => f.organismo))].sort());
	let niveles = $derived([...new Set(data.fuentes.flatMap((f) => f.niveles_publicados as string[]))].sort(
		(a, b) => orden(a) - orden(b)
	));
	const orden = (n: string) => (NIVELES as string[]).indexOf(n) + 1 || 99;
	let hayFiltros = $derived(Object.values(filtros).some(Boolean));
</script>

<svelte:head>
	<title>Fuentes · {NOMBRE_SITIO}</title>
</svelte:head>

<h1>Fuentes</h1>
<p>Los datos del observatorio salen de estas fuentes. Cada valor del sitio indica de qué archivo salió.</p>

<dl class="resumen">
	<div><dt>Activas</dt><dd>{numero(r.porEstado.activa)}</dd></div>
	<div><dt>En preparación</dt><dd>{numero(r.porEstado['en preparación'])}</dd></div>
	<div><dt>A relevar</dt><dd>{numero(r.porEstado['a relevar'])}</dd></div>
	<div><dt>Última revisión</dt><dd>{fecha(r.ultimaRevision)}</dd></div>
</dl>

<form class="filtros tarjeta" role="search" aria-label="Filtrar fuentes" onsubmit={(e) => e.preventDefault()}>
	<div class="campo texto">
		<label for="f-texto">Buscar</label>
		<input id="f-texto" type="search" bind:value={filtros.texto} placeholder="Nombre, organismo o tema" />
	</div>
	<div class="campo">
		<label for="f-organismo">Organismo</label>
		<select id="f-organismo" bind:value={filtros.organismo}>
			<option value="">Todos</option>
			{#each organismos as o (o)}<option value={o}>{o}</option>{/each}
		</select>
	</div>
	<div class="campo">
		<label for="f-nivel">Nivel</label>
		<select id="f-nivel" bind:value={filtros.nivel}>
			<option value="">Todos</option>
			{#each niveles as n (n)}<option value={n}>{etiquetaNivel(n)}</option>{/each}
		</select>
	</div>
	<div class="campo">
		<label for="f-estado">Estado</label>
		<select id="f-estado" bind:value={filtros.estado}>
			<option value="">Todos</option>
			{#each ESTADOS as e (e)}<option value={e}>{e}</option>{/each}
		</select>
	</div>
	{#if hayFiltros}
		<button type="button" class="limpiar" onclick={() => (filtros = { ...SIN_FILTROS })}>Limpiar filtros</button>
	{/if}
</form>

<p class="suave" role="status" aria-live="polite">
	{visibles.length === 1 ? '1 fuente' : `${numero(visibles.length)} fuentes`}{hayFiltros ? ' con estos filtros' : ''}.
</p>

<TablaDesplazable etiqueta="Fuentes de datos" clase="tarjeta">
	<table>
		<caption class="visualmente-oculto">Fuentes de datos</caption>
		<thead>
			<tr>
				<th scope="col">Fuente</th>
				<th scope="col">Temas</th>
				<th scope="col">Nivel más detallado</th>
				<th scope="col">Frecuencia</th>
				<th scope="col">Última captura</th>
				<th scope="col">Estado</th>
			</tr>
		</thead>
		<tbody>
			{#each visibles as f (f.id)}
				{@const ultima = data.ultimas[f.id]}
				<tr>
					<td>
						<a href={resolve('/fuentes/[id]', { id: f.id })}>{f.nombre}</a><br />
						<span class="suave">{f.organismo}</span>
					</td>
					<td>{f.temas.join(', ')}</td>
					<td>{etiquetaNivel(f.nivel_mas_detallado)}</td>
					<td>{f.frecuencia}</td>
					<td>{ultima ? fecha(ultima) : '—'}</td>
					<td><span class="estado estado-{f.estado.replace(' ', '-')}">{f.estado}</span></td>
				</tr>
			{:else}
				<tr><td colspan="6">Ninguna fuente cumple estos filtros.</td></tr>
			{/each}
		</tbody>
	</table>
</TablaDesplazable>

<section aria-labelledby="titulo-como">
	<h2 id="titulo-como">Cómo trabajamos con cada fuente</h2>
	<ol class="pasos">
		<li>
			<h3>Registrar</h3>
			<p>Cada fuente tiene una ficha técnica: organismo, licencia, formato, frecuencia y hasta qué nivel territorial publica.</p>
		</li>
		<li>
			<h3>Guardar el original</h3>
			<p>El archivo descargado se guarda sin cambios, con su huella sha256. Si no cambió, no se vuelve a procesar.</p>
		</li>
		<li>
			<h3>Procesar y controlar</h3>
			<p>
				Cada valor se guarda en el nivel en que la fuente lo publica, sin sumar hacia arriba. Si un control de calidad
				falla, no se publica nada.
			</p>
		</li>
		<li>
			<h3>Publicar</h3>
			<p>Los datos salen en el mapa, en las fichas y en <a href={resolve('/datos')}>descargas</a>, siempre con su fuente.</p>
		</li>
	</ol>
</section>

<style>
	.resumen {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: var(--espacio-3);
		margin: var(--espacio-4) 0;
	}

	.resumen div {
		background: var(--tarjeta);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		padding: var(--espacio-3) var(--espacio-4);
	}

	.resumen dt {
		font-size: var(--texto-s);
		color: var(--texto-suave);
	}

	.resumen dd {
		margin: 0;
		font-family: var(--fuente-titulos);
		font-size: var(--texto-xl);
		font-weight: 700;
	}

	.filtros {
		display: grid;
		grid-template-columns: 2fr repeat(3, 1fr) auto;
		gap: var(--espacio-3);
		align-items: end;
		padding: var(--espacio-4);
	}

	.campo {
		display: grid;
		gap: var(--espacio-1);
		min-width: 0;
	}

	label {
		font-size: var(--texto-s);
		font-weight: 600;
	}

	input,
	select,
	.limpiar {
		min-height: var(--toque-min);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		background: var(--tarjeta);
		padding: 0 var(--espacio-3);
		font: inherit;
		color: var(--texto);
		width: 100%;
	}

	.limpiar {
		color: var(--primario);
		font-weight: 600;
		cursor: pointer;
		width: auto;
	}

	td a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
		font-weight: 600;
	}

	.estado {
		display: inline-block;
		padding: 0 var(--espacio-2);
		border-radius: var(--radio-s);
		border: 1px solid var(--borde);
		white-space: nowrap;
	}

	.estado-activa {
		background: #e3f1e6;
		border-color: #5f9e6e;
		color: #1e5a2c;
	}

	.estado-en-preparación {
		background: var(--azul-1);
		color: var(--primario);
	}

	.estado-a-relevar {
		background: var(--aviso-fondo);
		border-color: var(--aviso-borde);
		color: var(--aviso-texto);
	}

	section {
		margin-top: var(--espacio-6);
	}

	.pasos {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: var(--espacio-4);
		padding: 0;
		list-style: none;
		counter-reset: paso;
	}

	.pasos li {
		background: var(--tarjeta);
		border: 1px solid var(--borde);
		border-radius: var(--radio-l);
		padding: var(--espacio-4);
		counter-increment: paso;
	}

	.pasos h3::before {
		content: counter(paso) '. ';
		color: var(--primario);
	}

	.pasos h3 {
		font-size: var(--texto-m);
		margin: 0 0 var(--espacio-2);
	}

	.pasos p {
		margin: 0;
	}

	@media (max-width: 800px) {
		.filtros {
			grid-template-columns: 1fr;
		}
	}
</style>
