<script lang="ts">
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import { NOMBRE_NIVEL, hrefFicha } from '#lib/datos.ts';
	import { numero } from '#lib/formato.ts';
	import { NOMBRE_SITIO } from '#lib/sitio.ts';

	let { data } = $props();
</script>

<svelte:head>
	<title>Fichas · {NOMBRE_SITIO}</title>
</svelte:head>

<h1>Fichas</h1>
<p>
	Cada territorio tiene una ficha con sus datos, de dónde salen y los territorios que contiene. Elegí un
	departamento para empezar{#each data.pais as p (p.id)}, o mirá la ficha de <a href={hrefFicha(p)}>{p.nombre}</a> (todo el país){/each}.
</p>

<TablaDesplazable etiqueta="Departamentos" clase="tarjeta">
	<table>
		<caption class="visualmente-oculto">Departamentos y cantidad de unidades que contienen</caption>
		<thead>
			<tr>
				<th scope="col">Departamento</th>
				<th scope="col">Código</th>
				<th scope="col" class="num">Secciones</th>
				<th scope="col" class="num">Segmentos</th>
				<th scope="col" class="num">Localidades</th>
			</tr>
		</thead>
		<tbody>
			{#each data.departamentos as d (d.id)}
				<tr>
					<td><a href={hrefFicha(d)}>{d.nombre}</a></td>
					<td>{d.codigo}</td>
					<td class="num">{numero(data.secciones[d.codigo] ?? 0)}</td>
					<td class="num">{numero(data.segmentos[d.codigo] ?? 0)}</td>
					<td class="num">{numero(data.localidades[d.codigo] ?? 0)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</TablaDesplazable>

{#if data.montevideo.length}
	<section>
		<h2>Montevideo: municipios, barrios y CCZ</h2>
		<ul class="grilla">
			{#each data.montevideo as t (t.id)}
				<li>
					<a href={hrefFicha(t)}>{t.nombre}</a>
					<span class="suave">· {NOMBRE_NIVEL[t.nivel]}</span>
				</li>
			{/each}
		</ul>
	</section>
{/if}

<style>
	section {
		margin-top: var(--espacio-5);
	}

	.grilla {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: var(--espacio-1) var(--espacio-4);
		list-style: none;
		padding: 0;
	}

	.grilla a,
	td a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
	}
</style>
