<script lang="ts">
	// Mini-mapa de ubicación (AC-M4): Uruguay con el territorio resaltado; los muy chicos, con un anillo.
	import { onMount } from 'svelte';
	import { leerJson } from '../datos.ts';
	import { COLOR_SELECCION } from './colores.ts';

	let {
		nombre,
		depto,
		nivel,
		bbox,
		resaltar = true
	}: {
		nombre: string;
		depto: string;
		nivel: string;
		bbox: [number, number, number, number];
		/** false: solo el contorno de Uruguay (vista previa del mapa). */
		resaltar?: boolean;
	} = $props();

	interface Mini {
		features: { properties: { codigo: string; nivel: string }; geometry: { type: string; coordinates: unknown } }[];
	}

	const ANCHO = 200;
	const ALTO = 180;
	const MARGEN = 8;
	// Encuadre fijo de Uruguay y proyección equirectangular corregida por latitud (~ -32.5°).
	const [O, S, E, N] = [-58.5, -35.05, -53.05, -30.05];
	const K = Math.cos((32.5 * Math.PI) / 180);
	const escala = Math.min((ANCHO - 2 * MARGEN) / ((E - O) * K), (ALTO - 2 * MARGEN) / (N - S));
	const x = (lon: number) => MARGEN + (lon - O) * K * escala;
	const y = (lat: number) => MARGEN + (N - lat) * escala;

	let deptos: { codigo: string; nivel: string; d: string }[] = $state([]);

	function camino(geom: { type: string; coordinates: unknown }): string {
		const poligonos = (geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates) as number[][][][];
		return poligonos
			.flatMap((p) => p.map((anillo) => 'M' + anillo.map(([lo, la]) => `${x(lo).toFixed(1)},${y(la).toFixed(1)}`).join('L') + 'Z'))
			.join('');
	}

	onMount(async () => {
		const mini = await leerJson<Mini>('uruguay_mini.geojson');
		deptos = mini.features.map((f) => ({ codigo: f.properties.codigo, nivel: f.properties.nivel, d: camino(f.geometry) }));
	});

	let caja = $derived({ x0: x(bbox[0]), y0: y(bbox[3]), x1: x(bbox[2]), y1: y(bbox[1]) });
	// Montevideo (~530 km²) mide unos 12 x 7 px: lleva anillo, como todo lo más chico.
	let chico = $derived(caja.x1 - caja.x0 < 16 && caja.y1 - caja.y0 < 16);
	let esDepto = $derived(nivel === 'departamento');
</script>

<svg viewBox="0 0 {ANCHO} {ALTO}" role="img" aria-label="Ubicación de {nombre} en Uruguay" class="mini">
	{#each deptos as d (d.codigo + d.nivel)}
		<path
			d={d.d}
			fill={esDepto && d.nivel === 'departamento' && d.codigo === depto ? COLOR_SELECCION : d.codigo === depto ? '#c3d7ec' : '#eaf1f8'}
			stroke="#8b96a1"
			stroke-width="0.6"
		/>
	{/each}
	{#if !resaltar}
		<!-- solo el contorno -->
	{:else if chico}
		<circle cx={(caja.x0 + caja.x1) / 2} cy={(caja.y0 + caja.y1) / 2} r="10" fill="none" stroke={COLOR_SELECCION} stroke-width="2.5" />
	{:else if !esDepto}
		<rect x={caja.x0} y={caja.y0} width={caja.x1 - caja.x0} height={caja.y1 - caja.y0} fill="none" stroke={COLOR_SELECCION} stroke-width="2" />
	{/if}
</svg>

<style>
	.mini {
		display: block;
		width: 100%;
		max-width: 220px;
		height: auto;
	}
</style>
