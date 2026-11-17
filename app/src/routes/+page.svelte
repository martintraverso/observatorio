<script lang="ts">
	import { NOMBRE_NIVEL, NIVELES, hrefFicha } from '#lib/datos.ts';
	import { numero } from '#lib/formato.ts';
	import { NOMBRE_SITIO } from '#lib/sitio.ts';

	let { data } = $props();
</script>

<svelte:head>
	<title>Mapa · {NOMBRE_SITIO}</title>
</svelte:head>

<h1>Mapa</h1>

<p class="aviso" role="status">
	El mapa interactivo todavía está en construcción. Mientras tanto, podés abrir la ficha de cada
	departamento.
</p>

<section class="tarjeta" aria-labelledby="titulo-territorios">
	<h2 id="titulo-territorios">Territorios cargados</h2>
	<ul class="conteos">
		{#each NIVELES.filter((n) => data.conteo[n]) as nivel (nivel)}
			<li><strong>{numero(data.conteo[nivel])}</strong> {NOMBRE_NIVEL[nivel].toLowerCase()}</li>
		{/each}
	</ul>
</section>

<section aria-labelledby="titulo-deptos">
	<h2 id="titulo-deptos">Departamentos</h2>
	<ul class="grilla">
		{#each data.departamentos as d (d.id)}
			<li><a href={hrefFicha(d)}>{d.nombre}</a> <span class="suave">· {d.codigo}</span></li>
		{/each}
	</ul>
</section>

<style>
	section {
		margin-top: var(--espacio-5);
	}

	.conteos {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-2) var(--espacio-5);
		list-style: none;
		padding: 0;
		margin: 0;
	}

	.grilla {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: var(--espacio-1) var(--espacio-4);
		list-style: none;
		padding: 0;
	}

	.grilla a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
	}
</style>
