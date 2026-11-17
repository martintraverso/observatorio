<script lang="ts">
	import '#lib/global.css';
	import Buscador from '#lib/Buscador.svelte';
	import favicon from '#lib/assets/favicon.svg';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { ATRIBUCION, NAVEGACION, NOMBRE_SITIO, URL_REPOSITORIO } from '#lib/sitio.ts';

	let { children } = $props();

	function activo(ruta: string): boolean {
		const actual = page.route.id ?? '';
		if (ruta === '/') return actual === '/';
		if (ruta === '/fichas') return actual === '/fichas' || actual.startsWith('/territorio');
		return actual.startsWith(ruta);
	}
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<a class="saltar" href="#contenido">Saltar al contenido</a>

<header class="encabezado">
	<div class="contenedor fila">
		<a class="marca" href={resolve('/')}>
			<svg aria-hidden="true" width="28" height="28" viewBox="0 0 28 28">
				<rect width="28" height="28" rx="8" fill="var(--primario)" />
				<path d="M7 18 L12 9 L16 15 L19 11 L22 18 Z" fill="var(--azul-2)" />
				<circle cx="19" cy="8" r="2.5" fill="var(--acento)" />
			</svg>
			<span>{NOMBRE_SITIO}</span>
		</a>

		<nav aria-label="Principal">
			<ul>
				{#each NAVEGACION as item (item.ruta)}
					<li>
						<a href={resolve(item.ruta)} aria-current={activo(item.ruta) ? 'page' : undefined}>
							{item.texto}
						</a>
					</li>
				{/each}
			</ul>
		</nav>

		<Buscador />
	</div>
</header>

<main id="contenido" class="contenedor">
	{@render children()}
</main>

<footer class="pie">
	<div class="contenedor">
		<p>
			{ATRIBUCION}. Según sus metadatos: «El uso es libre, citando como fuente al INE.»
			Cada valor indica de qué archivo salió; ver <a href={resolve('/fuentes')}>Fuentes</a>.
		</p>
		<p class="suave">
			Observatorio Uruguay · <a href={URL_REPOSITORIO}>Código y datos en GitHub</a>
		</p>
	</div>
</footer>

<style>
	.saltar {
		position: absolute;
		left: var(--espacio-4);
		top: -100px;
		background: var(--primario);
		color: var(--sobre-primario);
		padding: var(--espacio-2) var(--espacio-4);
		border-radius: var(--radio-s);
		z-index: 10;
	}

	.saltar:focus {
		top: var(--espacio-2);
	}

	.encabezado {
		background: var(--tarjeta);
		border-bottom: 1px solid var(--borde);
	}

	.fila {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--espacio-2) var(--espacio-5);
		padding-top: var(--espacio-2);
		padding-bottom: var(--espacio-2);
	}

	.marca {
		display: inline-flex;
		align-items: center;
		gap: var(--espacio-2);
		min-height: var(--toque-min);
		color: var(--texto);
		text-decoration: none;
		font-family: var(--fuente-titulos);
		font-weight: 700;
		font-size: var(--texto-l);
	}

	nav ul {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-1);
		list-style: none;
		margin: 0;
		padding: 0;
	}

	nav a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
		padding: 0 var(--espacio-3);
		border-radius: var(--radio-s);
		color: var(--texto);
		text-decoration: none;
		font-weight: 600;
	}

	nav a:hover {
		background: var(--azul-1);
	}

	nav a[aria-current='page'] {
		background: var(--azul-1);
		color: var(--primario);
		box-shadow: inset 0 -3px 0 var(--primario);
	}


	main {
		padding-top: var(--espacio-5);
		padding-bottom: var(--espacio-6);
		min-height: 60vh;
	}

	.pie {
		border-top: 1px solid var(--borde);
		background: var(--tarjeta);
		padding: var(--espacio-4) 0;
		font-size: var(--texto-s);
	}

	.pie p {
		margin: var(--espacio-1) 0;
	}
</style>
