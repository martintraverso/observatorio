<script lang="ts">
	// AC-V26: localizador de cerca para unidades chicas (segmento, sección, localidad): el territorio resaltado
	// entre sus vecinos del mismo nivel. Mapa estático de MapLibre sobre territorios.pmtiles, cargado recién
	// cuando se ve. Si el navegador no puede dibujarlo (sin WebGL2), no se muestra: queda el mini-mapa del país.
	import 'maplibre-gl/dist/maplibre-gl.css';
	import { onMount } from 'svelte';
	import type { Map as MapaLibre, StyleSpecification } from 'maplibre-gl';
	import { urlDatos } from '../datos.ts';
	import { ATRIBUCION_MAPA, COLOR_SELECCION } from './colores.ts';
	import { cargarMapLibre } from './cargar.ts';

	let {
		nombre,
		nivel,
		id,
		bbox,
		minzoom = 0
	}: {
		nombre: string;
		nivel: string;
		id: string;
		bbox: [number, number, number, number];
		/** Zoom desde el que el nivel está en el PMTiles (catálogo de niveles, M11.2). */
		minzoom?: number;
	} = $props();

	let contenedor: HTMLDivElement | undefined = $state();
	// Las localidades no cubren el territorio (entre pueblos no hay otra localidad): su contexto son las secciones.
	const contexto = $derived(nivel === 'localidad' ? 'seccion' : nivel);
	let sinMapa = $state(false);

	/** La caja del territorio, agrandada para que se vean sus vecinos. */
	function entorno([o, s, e, n]: [number, number, number, number]): [[number, number], [number, number]] {
		const dx = Math.max(e - o, 0.002);
		const dy = Math.max(n - s, 0.002);
		return [
			[o - dx, s - dy],
			[e + dx, n + dy]
		];
	}

	/** Estilo del mapa. `grande`: segmento que no entra al zoom de los segmentos (contexto: secciones + su caja). */
	function estilo(grande: boolean): StyleSpecification {
		const capa = grande ? 'seccion' : contexto;
		const [o, s, e, n] = bbox;
		return {
			version: 8,
			sources: {
				territorios: { type: 'vector', url: `pmtiles://${new URL(urlDatos('territorios.pmtiles'), location.href).href}` },
				caja: {
					type: 'geojson',
					data: {
						type: 'Feature',
						properties: {},
						geometry: { type: 'Polygon', coordinates: [[[o, s], [e, s], [e, n], [o, n], [o, s]]] }
					}
				}
			},
			layers: [
				{ id: 'fondo', type: 'background', paint: { 'background-color': '#f6f7f5' } },
				{ id: 'cerca-vecinos', type: 'fill', source: 'territorios', 'source-layer': capa, paint: { 'fill-color': '#eaf1f8' } },
				grande
					? { id: 'cerca-caja', type: 'line', source: 'caja', paint: { 'line-color': COLOR_SELECCION, 'line-width': 2.5 } }
					: {
							id: 'cerca-seleccion',
							type: 'fill',
							source: 'territorios',
							'source-layer': nivel,
							filter: ['==', ['get', 'id'], id],
							paint: { 'fill-color': COLOR_SELECCION }
						},
				{ id: 'cerca-bordes', type: 'line', source: 'territorios', 'source-layer': capa, paint: { 'line-color': '#8b96a1', 'line-width': 0.8 } }
			]
		};
	}

	onMount(() => {
		let mapa: MapaLibre | null = null;
		let destruido = false;
		const iniciar = async () => {
			let maplibregl: Awaited<ReturnType<typeof cargarMapLibre>>;
			try {
				maplibregl = await cargarMapLibre();
			} catch {
				sinMapa = true; // no se pudo bajar MapLibre: queda el mini-mapa del país
				return;
			}
			if (destruido) return;
			try {
				mapa = new maplibregl.Map({
					container: contenedor!,
					bounds: entorno(bbox),
					fitBoundsOptions: { padding: 8, maxZoom: 15 },
					interactive: false,
					attributionControl: false, // la atribución va en el pie, para no tapar un mapa tan chico
					style: estilo(false)
				});
				// Los segmentos están en el PMTiles desde su zoom mínimo. Un segmento rural grande no entra a ese zoom:
				// se muestra con las secciones como contexto y el rectángulo que ocupa, en vez de un mapa en blanco.
				if (minzoom > 0 && mapa.getZoom() < minzoom) mapa.setStyle(estilo(true));
				// Para los tests e2e.
				(window as unknown as { __localizador?: MapaLibre }).__localizador = mapa;
			} catch {
				sinMapa = true;
			}
		};
		let observador: IntersectionObserver | null = null;
		if ('IntersectionObserver' in window) {
			observador = new IntersectionObserver((entradas) => {
				if (entradas.some((e) => e.isIntersecting)) {
					observador?.disconnect();
					iniciar();
				}
			});
			if (contenedor) observador.observe(contenedor);
		} else {
			iniciar();
		}
		return () => {
			destruido = true;
			observador?.disconnect();
			mapa?.remove();
		};
	});
</script>

{#if !sinMapa}
	<figure class="cerca">
		<div class="lienzo" bind:this={contenedor} role="img" aria-label="{nombre} y sus vecinos, de cerca"></div>
		<figcaption class="suave">De cerca, con sus vecinos · {ATRIBUCION_MAPA}</figcaption>
	</figure>
{/if}

<style>
	.cerca {
		margin: var(--espacio-2) 0 0;
	}

	.lienzo {
		width: 100%;
		aspect-ratio: 4 / 3;
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		overflow: hidden;
		background: var(--fondo);
	}

	figcaption {
		margin-top: var(--espacio-1);
		font-size: var(--texto-xs);
	}
</style>
