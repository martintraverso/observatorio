<script lang="ts">
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import { resolve } from '$app/paths';
	import { NOMBRE_NIVEL, NIVELES, partesId, hrefFicha, type Relacion } from '#lib/datos.ts';
	import { fecha, numero } from '#lib/formato.ts';
	import { NOMBRE_SITIO } from '#lib/sitio.ts';

	let { data } = $props();
	let f = $derived(data.ficha);

	// Cuántas filas de cada nivel se listan en "Dentro de este territorio" antes de resumir.
	const MAX_FILAS = 300;

	let contenidos = $derived(NIVELES.filter((n) => f.contenidos[n]?.length).map((n) => [n, f.contenidos[n]!] as const));

	function fuenteDe(capturaId: string): string {
		const c = f.capturas[capturaId];
		const fuente = c && f.fuentes[c.fuente_id];
		return fuente ? `${fuente.organismo} · ${fuente.nombre}` : capturaId;
	}

	function textoRelacion(r: Relacion): string {
		if (r.existe) return r.nombre ?? r.codigo;
		if (r.codigo.endsWith('900')) return `Zona rural (código ${r.codigo}; el INE no publica un polígono de localidad)`;
		return `Código ${r.codigo} (el INE no publica un polígono de localidad)`;
	}
</script>

<svelte:head>
	<title>{f.nombre} · {NOMBRE_NIVEL[f.nivel]} · {NOMBRE_SITIO}</title>
</svelte:head>

<nav aria-label="Ubicación" class="migas">
	<ol>
		<li><a href={resolve('/fichas')}>Uruguay</a></li>
		{#each f.padres as p (p.id)}
			<li><a href={hrefFicha(p)}>{p.nombre}</a></li>
		{/each}
		<li aria-current="page">{f.nombre}</li>
	</ol>
</nav>

<h1>{f.nombre}</h1>
<p class="chips">
	<span class="chip">{NOMBRE_NIVEL[f.nivel]}</span>
	<span class="chip">Código INE {f.codigo}</span>
	{#if f.area_km2 !== null}<span class="chip">{numero(f.area_km2, 1)} km²</span>{/if}
</p>

{#each f.relaciones as r (r.destino_id)}
	<p>
		Pertenece a la localidad:
		{#if r.existe}
			<a href={hrefFicha(partesId(r.destino_id))}>{textoRelacion(r)}</a>
		{:else}
			{textoRelacion(r)}
		{/if}
	</p>
{/each}

<section class="tarjeta" aria-labelledby="titulo-datos">
	<h2 id="titulo-datos">Datos</h2>
	{#if f.observaciones.length === 0}
		<p class="aviso">
			Este territorio no tiene datos propios.
			{#if f.nivel === 'area_especial'}El INE repite en este polígono los conteos de Artigas, por eso no se
				guardan.{/if}
		</p>
	{:else}
		<TablaDesplazable etiqueta="Datos de {f.nombre}">
			<table>
				<caption class="visualmente-oculto">Datos de {f.nombre}</caption>
				<thead>
					<tr>
						<th scope="col">Indicador</th>
						<th scope="col" class="num">Valor</th>
						<th scope="col">Período</th>
						<th scope="col">Fuente</th>
					</tr>
				</thead>
				<tbody>
					{#each f.observaciones as o (o.indicador + o.periodo)}
						<tr>
							<td>{f.indicadores[o.indicador]?.nombre ?? o.indicador}</td>
							<td class="num">
								{numero(o.valor)}
								{f.indicadores[o.indicador]?.unidad}
								{#if o.es_estimado}<span class="estimado">estimado</span>{/if}
							</td>
							<td>{o.periodo}</td>
							<td>{fuenteDe(o.captura_id)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</TablaDesplazable>
	{/if}
</section>

{#if contenidos.length}
	<section aria-labelledby="titulo-dentro">
		<h2 id="titulo-dentro">Dentro de {f.nombre}</h2>
		{#each contenidos as [nivel, lista] (nivel)}
			<details open={lista.length <= 50}>
				<summary>{NOMBRE_NIVEL[nivel]}: {numero(lista.length)}</summary>
				<TablaDesplazable etiqueta="{NOMBRE_NIVEL[nivel]} dentro de {f.nombre}">
					<table>
						<caption class="visualmente-oculto">{NOMBRE_NIVEL[nivel]} dentro de {f.nombre}</caption>
						<thead>
							<tr>
								<th scope="col">Nombre</th>
								<th scope="col">Código</th>
								<th scope="col" class="num">Personas (2023)</th>
								<th scope="col" class="num">Viviendas (2023)</th>
							</tr>
						</thead>
						<tbody>
							{#each lista.slice(0, MAX_FILAS) as h (h.id)}
								<tr>
									<td><a href={hrefFicha(h)}>{h.nombre}</a></td>
									<td>{h.codigo}</td>
									<td class="num">{numero(h.valores.pob_total?.['2023'])}</td>
									<td class="num">{numero(h.valores.viviendas_total?.['2023'])}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</TablaDesplazable>
				{#if lista.length > MAX_FILAS}
					<p class="suave">
						Se muestran {numero(MAX_FILAS)} de {numero(lista.length)}. La lista completa está en la ficha de
						cada sección.
					</p>
				{/if}
			</details>
		{/each}
	</section>
{/if}

<section aria-labelledby="titulo-fuentes">
	<h2 id="titulo-fuentes">Fuentes de esta ficha</h2>
	<ul>
		{#each Object.values(f.capturas) as c (c.id)}
			<li>
				<strong>{f.fuentes[c.fuente_id]?.nombre}</strong> ({f.fuentes[c.fuente_id]?.organismo}). Archivo
				<code>{c.archivo}</code>, sha256 <code>{c.sha256.slice(0, 12)}…</code>, procesado el {fecha(c.fecha_proceso)}.
				Licencia: {f.fuentes[c.fuente_id]?.licencia}
			</li>
		{/each}
	</ul>
</section>

<style>
	section {
		margin-top: var(--espacio-5);
	}

	.migas ol {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-1);
		list-style: none;
		padding: 0;
		margin: 0 0 var(--espacio-3);
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

	.estimado {
		display: inline-block;
		margin-left: var(--espacio-2);
		padding: 0 var(--espacio-2);
		border: 1px solid var(--aviso-borde);
		border-radius: var(--radio-s);
		color: var(--aviso-texto);
		background: var(--aviso-fondo);
		font-size: var(--texto-xs);
	}

	details {
		margin: var(--espacio-3) 0;
	}

	summary {
		min-height: var(--toque-min);
		display: flex;
		align-items: center;
		cursor: pointer;
		font-weight: 600;
	}

	td a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
	}

	code {
		font-size: var(--texto-xs);
		overflow-wrap: anywhere;
	}
</style>
