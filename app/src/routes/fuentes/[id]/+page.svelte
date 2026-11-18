<script lang="ts">
	// Detalle de una fuente (M8, AC-SRC3, AC-SRC4).
	import { resolve } from '$app/paths';
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import { etiquetaNivel } from '#lib/datos.ts';
	import { fecha, numero } from '#lib/formato.ts';
	import { TEXTO_RESULTADO } from '#lib/fuentes.ts';
	import { NOMBRE_SITIO, URL_REPOSITORIO } from '#lib/sitio.ts';

	let { data } = $props();
	let f = $derived(data.fuente);
	let reportar = $derived(
		`${URL_REPOSITORIO}/issues/new?title=${encodeURIComponent(`Fuente ${f.id}: `)}&body=${encodeURIComponent(
			`Fuente: ${f.nombre} (${f.id})\n\nQué encontré:\n`
		)}`
	);
	const nivel = etiquetaNivel;
</script>

<svelte:head>
	<title>{f.nombre} · Fuentes · {NOMBRE_SITIO}</title>
</svelte:head>

<nav aria-label="Ubicación" class="migas">
	<ol>
		<li><a href={resolve('/fuentes')}>Fuentes</a></li>
		<li aria-current="page">{f.nombre}</li>
	</ol>
</nav>

<h1>{f.nombre}</h1>
<p class="chips">
	<span class="chip">{f.organismo}</span>
	<span class="chip estado">{f.estado}</span>
	{#each f.temas as t (t)}<span class="chip">{t}</span>{/each}
</p>

<div class="columnas">
	<section class="tarjeta" aria-labelledby="titulo-tecnica">
		<h2 id="titulo-tecnica">Ficha técnica</h2>
		<dl class="tecnica">
			<div><dt>Organismo</dt><dd>{f.organismo}</dd></div>
			<div><dt>Página</dt><dd><a href={f.pagina}>{f.pagina}</a></dd></div>
			<div><dt>Descarga</dt><dd><a href={f.url_descarga}>{f.url_descarga}</a></dd></div>
			{#if f.archivo_original}<div><dt>Archivo original</dt><dd><code>{f.archivo_original}</code></dd></div>{/if}
			<div><dt>Formato</dt><dd>{f.formato}</dd></div>
			<div><dt>Frecuencia</dt><dd>{f.frecuencia}</dd></div>
			{#if f.version_geo}<div><dt>Versión geográfica</dt><dd>{f.version_geo}</dd></div>{/if}
			<div><dt>Licencia</dt><dd class="literal">{f.licencia}</dd></div>
			<div><dt>Contacto</dt><dd class="literal">{f.contacto ?? '—'}</dd></div>
		</dl>
	</section>

	<section class="tarjeta" aria-labelledby="titulo-alcance">
		<h2 id="titulo-alcance">Hasta dónde llega en el territorio</h2>
		<p>Nivel más detallado: <strong>{nivel(f.nivel_mas_detallado)}</strong>.</p>
		<ul class="niveles">
			{#each f.niveles_publicados as n (n)}
				<li>{nivel(n)} <span class="suave">· {numero(data.territoriosPorNivel[n] ?? 0)} territorios</span></li>
			{/each}
		</ul>
		<p class="suave">Los valores se guardan solo en estos niveles: no se suman hacia niveles mayores.</p>
	</section>
</div>

<section class="tarjeta" aria-labelledby="titulo-indicadores">
	<h2 id="titulo-indicadores">Indicadores que salen de esta fuente</h2>
	{#if data.indicadores.length}
		<TablaDesplazable etiqueta="Indicadores de {f.nombre}">
			<table>
				<caption class="visualmente-oculto">Indicadores de {f.nombre}</caption>
				<thead>
					<tr>
						<th scope="col">Indicador</th>
						<th scope="col">Unidad</th>
						<th scope="col">Tema</th>
						<th scope="col">Columna original</th>
						<th scope="col">Períodos</th>
					</tr>
				</thead>
				<tbody>
					{#each data.indicadores as i (i.codigo)}
						<tr>
							<td>{i.nombre} <span class="suave">({i.codigo})</span></td>
							<td>{i.unidad}</td>
							<td>{i.tema}</td>
							<td><code>{i.columna_origen}</code></td>
							<td>{i.periodos.join(', ')}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</TablaDesplazable>
		{#if data.indicadores[0]?.nota}<p class="suave nota">{data.indicadores[0].nota}</p>{/if}
	{:else}
		<p class="aviso">Esta fuente todavía no aporta indicadores.</p>
	{/if}
</section>

<section class="tarjeta" aria-labelledby="titulo-capturas">
	<h2 id="titulo-capturas">Historial de capturas</h2>
	{#if data.historial.length}
		<TablaDesplazable etiqueta="Capturas de {f.nombre}">
			<table>
				<caption class="visualmente-oculto">Capturas de {f.nombre}</caption>
				<thead>
					<tr>
						<th scope="col">Fecha</th>
						<th scope="col">Archivo</th>
						<th scope="col">sha256</th>
						<th scope="col">Resultado</th>
					</tr>
				</thead>
				<tbody>
					{#each data.historial as c, i (c.id + c.fecha_proceso + c.resultado + i)}
						<tr>
							<td>{fecha(c.fecha_proceso)}</td>
							<td><code>{c.archivo}</code></td>
							<td><code title={c.sha256}>{c.sha256.slice(0, 12)}…</code></td>
							<td>
								<span class="resultado resultado-{c.resultado.replace(' ', '-')}">{TEXTO_RESULTADO[c.resultado]}</span>
								{#if c.detalle}<span class="suave detalle">{c.detalle}</span>{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</TablaDesplazable>
	{:else}
		<p class="aviso">Todavía no hay capturas de esta fuente.</p>
	{/if}
</section>

{#if f.notas.length}
	<section class="tarjeta" aria-labelledby="titulo-notas">
		<h2 id="titulo-notas">Notas y advertencias</h2>
		<ul>
			{#each f.notas as n (n)}<li>{n}</li>{/each}
		</ul>
	</section>
{/if}

<section aria-labelledby="titulo-reportar">
	<h2 id="titulo-reportar">¿Encontraste un problema?</h2>
	<p>
		Si un dato no coincide con la fuente o algo no se entiende, <a href={reportar}>reportalo en GitHub</a>
		(necesitás una cuenta).
	</p>
</section>

<style>
	section {
		margin-top: var(--espacio-5);
	}

	.migas ol {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--espacio-1);
		list-style: none;
		padding: 0;
		margin: 0 0 var(--espacio-2);
		font-size: var(--texto-s);
	}

	.migas li + li::before {
		content: '›';
		margin-right: var(--espacio-1);
		color: var(--texto-suave);
	}

	.migas a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-2);
	}

	.chip {
		background: var(--azul-1);
		border: 1px solid var(--borde);
		border-radius: 999px;
		padding: var(--espacio-1) var(--espacio-3);
		font-size: var(--texto-s);
	}

	.columnas {
		display: grid;
		grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
		gap: var(--espacio-4);
	}

	.columnas section {
		margin-top: var(--espacio-4);
	}

	.tecnica {
		margin: 0;
		display: grid;
		gap: var(--espacio-2);
	}

	.tecnica div {
		display: grid;
		grid-template-columns: 160px minmax(0, 1fr);
		gap: var(--espacio-3);
		border-bottom: 1px solid var(--borde);
		padding-bottom: var(--espacio-2);
	}

	.tecnica dt {
		font-weight: 600;
		font-size: var(--texto-s);
	}

	.tecnica dd {
		margin: 0;
		overflow-wrap: anywhere;
	}

	.literal {
		white-space: pre-wrap;
	}

	.niveles {
		padding-left: var(--espacio-5);
	}

	code {
		font-size: var(--texto-xs);
		overflow-wrap: anywhere;
	}

	.resultado {
		display: inline-block;
		padding: 0 var(--espacio-2);
		border-radius: var(--radio-s);
		border: 1px solid var(--borde);
		white-space: nowrap;
	}

	.resultado-nuevo,
	.resultado-reprocesado {
		background: #e3f1e6;
		border-color: #5f9e6e;
		color: #1e5a2c;
	}

	.resultado-error {
		background: var(--aviso-fondo);
		border-color: var(--aviso-borde);
		color: var(--aviso-texto);
	}

	.detalle {
		display: block;
		font-size: var(--texto-xs);
	}

	.nota {
		font-size: var(--texto-s);
	}

	@media (max-width: 800px) {
		.columnas {
			grid-template-columns: minmax(0, 1fr);
		}

		.tecnica div {
			grid-template-columns: minmax(0, 1fr);
			gap: 0;
		}
	}
</style>
