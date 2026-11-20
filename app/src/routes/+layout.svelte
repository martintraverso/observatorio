<script lang="ts">
	import '#lib/global.css';
	import Buscador from '#lib/Buscador.svelte';
	import favicon from '#lib/assets/favicon.svg';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { NAVEGACION, NOMBRE_SITIO, URL_REPOSITORIO } from '#lib/sitio.ts';

	let { children, data } = $props();
	/** "Instituto Nacional de Estadística (INE)" -> "INE". */
	// en la página de error el layout puede no traer datos
	let fuentesPie = $derived(data?.fuentesActivas ?? []);
	const siglas = (organismo: string) => organismo.replace(/^.*\((\w+)\)$/, '$1');

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
			<span class="nombre">{NOMBRE_SITIO}</span>
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

<main id="contenido" class={page.route.id === '/' ? 'pantalla-completa' : 'contenedor'}>
	{@render children()}
</main>

<footer class="pie">
	<div class="contenedor">
		<!-- AC-V29: todas las fuentes activas, desde fuentes.json -->
		<p>
			{fuentesPie.length === 1 ? 'Fuente' : 'Fuentes'}:
			{#each fuentesPie as f, i (f.id)}{i > 0 ? ' · ' : ''}<a href={resolve('/fuentes/[id]', { id: f.id })}
					>{siglas(f.organismo)}, {f.nombre}</a
				>{/each}. Cada valor indica de qué archivo salió y con qué licencia; ver <a href={resolve('/fuentes')}>Fuentes</a>.
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


	/* AC-V14: en celular, dos filas (logo + navegación; búsqueda), ≤ 120 px. El nombre queda para lectores de pantalla. */
	@media (max-width: 640px) {
		.fila {
			display: grid;
			grid-template-columns: auto minmax(0, 1fr);
			gap: var(--espacio-2);
		}

		/* el logo solo, con área táctil de 44 px (AC-G5) */
		.marca {
			min-width: var(--toque-min);
			justify-content: center;
		}

		.marca .nombre {
			position: absolute;
			width: 1px;
			height: 1px;
			margin: -1px;
			padding: 0;
			border: 0;
			overflow: hidden;
			clip: rect(0 0 0 0);
			white-space: nowrap;
		}

		nav ul {
			flex-wrap: nowrap;
			justify-content: flex-end;
			gap: 0;
		}

		nav a {
			padding: 0 var(--espacio-2);
		}

		.fila > :global(.buscar) {
			grid-column: 1 / -1;
			margin-left: 0;
		}
	}

	/* en los celulares más angostos (320 px) la navegación entra junto al logo sin pisarlo */
	@media (max-width: 360px) {
		.fila {
			gap: var(--espacio-1);
		}

		nav a {
			padding: 0 var(--espacio-1);
			font-size: var(--texto-s);
		}
	}

	main {
		flex: 1 0 auto;
	}

	main.contenedor {
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
