<script lang="ts" module>
	// El protocolo pmtiles:// se registra una sola vez por página.
	let protocoloRegistrado = false;
</script>

<script lang="ts">
	// Mapa de MapLibre GL sobre territorios.pmtiles (M6, AC-M1). Sin mapa base: los límites del INE sobre el fondo.
	import 'maplibre-gl/dist/maplibre-gl.css';
	import { onMount } from 'svelte';
	import type { Map as MapaLibre, MapLayerMouseEvent } from 'maplibre-gl';
	import { urlDatos } from '../datos.ts';
	import { ATRIBUCION_MAPA, COLOR_SIN_DATO, coloresClases } from './colores.ts';
	import { clase, NIVELES_MAPA, type Clases, type NivelMapa, ZOOM_SEGMENTOS } from './estado.ts';
	import MiniMapa from './MiniMapa.svelte';
	import { LOCALE_MAPA } from './idioma.ts';

	let {
		nivel,
		valores,
		clases,
		seleccionado,
		onseleccionar,
		onzoom
	}: {
		nivel: NivelMapa;
		/** codigo -> valor del indicador y período elegidos, en el nivel elegido. */
		valores: Record<string, number | null>;
		clases: Clases | null;
		/** id del territorio seleccionado ("INE-2023/seccion/1605"), o null. */
		seleccionado: string | null;
		onseleccionar: (id: string) => void;
		onzoom?: (zoom: number) => void;
	} = $props();

	const FUENTE = 'territorios';
	const NIVELES = NIVELES_MAPA; // capas que se pintan (incluye municipio_mvd, F2.8b)
	// Capas del PMTiles donde puede estar un territorio seleccionado (también desde la búsqueda).
	const NIVELES_SELECCION = ['departamento', 'area_especial', 'municipio_mvd', 'seccion', 'segmento', 'localidad', 'barrio_mvd', 'ccz_mvd'];
	const URUGUAY: [[number, number], [number, number]] = [
		[-58.5, -35.05],
		[-53.05, -30.05]
	];

	let contenedor: HTMLDivElement;
	let mapa: MapaLibre | null = $state(null);
	let listo = $state(false);
	let nombreBajoCursor = $state('');
	let sinMapa = $state(false);
	let esperandoToque = $state(false);
	let iniciarMapa: (() => void) | null = null;
	let pintado: { nivel: string; ids: string[] } = { nivel: '', ids: [] };

	let pendiente: [number, number, number, number] | null = null;

	/** Encuadra un territorio (bbox [oeste, sur, este, norte]); si el mapa no está listo, al cargar. */
	export function enfocar(bbox: [number, number, number, number]) {
		if (!mapa || !listo) {
			pendiente = bbox;
			return;
		}
		mapa.fitBounds(
			[
				[bbox[0], bbox[1]],
				[bbox[2], bbox[3]]
			],
			{ padding: 40, maxZoom: 13, duration: 600 }
		);
	}

	onMount(() => {
		let destruido = false;
		const iniciar = async () => {
			const [maplibregl, { Protocol }, { default: urlWorker }] = await Promise.all([
				import('maplibre-gl'),
				import('pmtiles'),
				// MapLibre 6 corre en un worker de módulo aparte; Vite lo copia y da su URL.
				import('maplibre-gl/dist/maplibre-gl-worker.mjs?url')
			]);
			if (destruido) return;
			if (!protocoloRegistrado) {
				maplibregl.setWorkerUrl(urlWorker);
				maplibregl.addProtocol('pmtiles', new Protocol().tile);
				protocoloRegistrado = true;
			}
			const pmtiles = new URL(urlDatos('territorios.pmtiles'), location.href).href;
			let m: MapaLibre;
			try {
				m = new maplibregl.Map({
					container: contenedor,
					bounds: URUGUAY,
					fitBoundsOptions: { padding: 16 },
					minZoom: 5,
					maxZoom: 15,
					maxBounds: [
						[-62, -38],
						[-49, -27]
					],
					dragRotate: false,
					pitchWithRotate: false,
					attributionControl: { compact: false, customAttribution: ATRIBUCION_MAPA },
					locale: LOCALE_MAPA,
					style: {
						version: 8,
						sources: { [FUENTE]: { type: 'vector', url: `pmtiles://${pmtiles}`, promoteId: 'id' } },
						layers: [
							{ id: 'fondo', type: 'background', paint: { 'background-color': '#f6f7f5' } },
							...NIVELES.flatMap((n) => [
								{
									id: `relleno-${n}`,
									type: 'fill' as const,
									source: FUENTE,
									'source-layer': n,
									...(n === 'segmento' ? { minzoom: ZOOM_SEGMENTOS } : {}),
									layout: { visibility: 'none' as const },
									paint: { 'fill-color': COLOR_SIN_DATO, 'fill-opacity': 0.92 }
								},
								{
									id: `borde-${n}`,
									type: 'line' as const,
									source: FUENTE,
									'source-layer': n,
									...(n === 'segmento' ? { minzoom: ZOOM_SEGMENTOS } : {}),
									layout: { visibility: 'none' as const },
									paint: { 'line-color': '#ffffff', 'line-width': 0.6 }
								}
							]),
							{
								id: 'contorno-departamentos',
								type: 'line',
								source: FUENTE,
								'source-layer': 'departamento',
								paint: { 'line-color': '#4f5b67', 'line-width': 1.2 }
							},
							...NIVELES_SELECCION.map((n) => ({
								id: `seleccion-${n}`,
								type: 'line' as const,
								source: FUENTE,
								'source-layer': n,
								filter: ['==', ['get', 'id'], ''] as ['==', ['get', string], string],
								paint: { 'line-color': '#e07a1f', 'line-width': 3.5 }
							}))
						]
					}
				});
			} catch (e) {
				// Sin WebGL2 (equipos viejos, aceleración gráfica desactivada) MapLibre no puede dibujar.
				console.warn('Mapa no disponible:', e);
				sinMapa = true;
				return;
			}
			m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
			m.getCanvas().setAttribute('aria-label', 'Mapa de Uruguay con los límites del INE');
			for (const n of NIVELES) {
				m.on('click', `relleno-${n}`, (e: MapLayerMouseEvent) => {
					const id = e.features?.[0]?.properties?.id;
					if (typeof id === 'string') onseleccionar(id);
				});
				m.on('mousemove', `relleno-${n}`, (e: MapLayerMouseEvent) => {
					m.getCanvas().style.cursor = 'pointer';
					nombreBajoCursor = String(e.features?.[0]?.properties?.nombre ?? '');
				});
				m.on('mouseleave', `relleno-${n}`, () => {
					m.getCanvas().style.cursor = '';
					nombreBajoCursor = '';
				});
			}
			m.on('zoomend', () => onzoom?.(m.getZoom()));
			m.on('load', () => {
				listo = true;
				onzoom?.(m.getZoom());
				if (pendiente) {
					enfocar(pendiente);
					pendiente = null;
				}
			});
			mapa = m;
			// Para los tests e2e (ubicar territorios en pantalla).
			(window as unknown as { __mapa?: MapaLibre }).__mapa = m;
		};
		// MapLibre es lo más pesado de la página.
		// En móvil arranca al tocar el mapa: así no se carga si no se usa, y el mapa no "atrapa" el
		// desplazamiento de la página. En escritorio, cuando al menos un cuarto del mapa se ve.
		let observador: IntersectionObserver | null = null;
		iniciarMapa = () => {
			esperandoToque = false;
			iniciar();
		};
		if (matchMedia('(max-width: 900px)').matches) {
			esperandoToque = true;
		} else if ('IntersectionObserver' in window) {
			observador = new IntersectionObserver(
				(entradas) => {
					if (entradas.some((e) => e.isIntersecting)) {
						observador?.disconnect();
						iniciar();
					}
				},
				{ threshold: 0.25 }
			);
			observador.observe(contenedor);
		} else {
			iniciar();
		}
		return () => {
			destruido = true;
			observador?.disconnect();
			mapa?.remove();
		};
	});

	// Nivel visible y valores pintados (feature-state "clase").
	$effect(() => {
		const m = mapa;
		if (!m || !listo) return;
		for (const n of NIVELES) {
			const v = n === nivel ? 'visible' : 'none';
			m.setLayoutProperty(`relleno-${n}`, 'visibility', v);
			m.setLayoutProperty(`borde-${n}`, 'visibility', v);
		}
		if (pintado.nivel) m.removeFeatureState({ source: FUENTE, sourceLayer: pintado.nivel });
		const colores = coloresClases(clases ? clases.cortes.length + 1 : 0);
		const ids: string[] = [];
		for (const [codigo, valor] of Object.entries(valores)) {
			if (valor === null || !clases) continue;
			const id = `INE-2023/${nivel}/${codigo}`;
			m.setFeatureState({ source: FUENTE, sourceLayer: nivel, id }, { clase: clase(valor, clases) });
			ids.push(id);
		}
		pintado = { nivel, ids };
		const expresion = colores.length
			? ['match', ['coalesce', ['feature-state', 'clase'], -1], ...colores.flatMap((c, i) => [i, c]), COLOR_SIN_DATO]
			: COLOR_SIN_DATO;
		m.setPaintProperty(`relleno-${nivel}`, 'fill-color', expresion as never);
	});

	// Territorio seleccionado: contorno naranja en su capa.
	$effect(() => {
		const m = mapa;
		if (!m || !listo) return;
		const nivelSel = seleccionado?.split('/')[1];
		for (const n of NIVELES_SELECCION) {
			m.setFilter(`seleccion-${n}`, ['==', ['get', 'id'], n === nivelSel ? seleccionado! : '']);
		}
	});
</script>

<div class="mapa" bind:this={contenedor} role="region" aria-label="Mapa">
	{#if nombreBajoCursor}
		<div class="etiqueta" aria-hidden="true">{nombreBajoCursor}</div>
	{/if}
	{#if esperandoToque}
		<div class="previa">
			<div class="contorno" aria-hidden="true">
				<MiniMapa nombre="Uruguay" depto="" nivel="pais" bbox={[-58.5, -35.05, -53.05, -30.05]} resaltar={false} />
			</div>
			<button type="button" class="activar" onclick={() => iniciarMapa?.()}>Ver el mapa interactivo</button>
		</div>
	{/if}
	{#if sinMapa}
		<div class="sin-mapa aviso" role="status">
			<p>Este navegador no puede dibujar el mapa (necesita WebGL2).</p>
			<p>Los mismos datos están en las fichas de cada territorio, en el buscador y en las descargas.</p>
		</div>
	{/if}
</div>

<style>
	.mapa {
		position: relative;
		width: 100%;
		height: 100%;
		min-height: 320px;
		background: var(--fondo);
	}

	.previa {
		position: absolute;
		inset: 0;
		z-index: 2;
		display: grid;
		place-items: center;
		align-content: center;
		gap: var(--espacio-4);
		background: var(--fondo);
	}

	.contorno {
		width: min(70%, 260px);
		opacity: 0.8;
	}

	.activar {
		min-height: var(--toque-min);
		padding: 0 var(--espacio-5);
		border: 0;
		border-radius: var(--radio-m);
		background: var(--primario);
		color: var(--sobre-primario);
		font: inherit;
		font-weight: 600;
		cursor: pointer;
	}

	.sin-mapa {
		position: absolute;
		inset: var(--espacio-4);
		height: fit-content;
		z-index: 2;
	}

	.sin-mapa p {
		margin: 0 0 var(--espacio-2);
	}

	.etiqueta {
		position: absolute;
		top: var(--espacio-2);
		left: var(--espacio-2);
		z-index: 2;
		background: var(--tarjeta);
		border: 1px solid var(--borde);
		border-radius: var(--radio-s);
		padding: var(--espacio-1) var(--espacio-2);
		font-size: var(--texto-s);
		pointer-events: none;
	}

	:global(.maplibregl-ctrl-attrib) {
		font-size: var(--texto-xs);
	}

	:global(.maplibregl-ctrl-group button) {
		width: var(--toque-min);
		height: var(--toque-min);
	}
</style>
