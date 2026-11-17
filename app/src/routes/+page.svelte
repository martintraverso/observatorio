<script lang="ts">
	// Pantalla Mapa (M6): tema → indicador → nivel → período; coropleta; panel del territorio.
	import { onMount, untrack } from 'svelte';
	import { replaceState } from '$app/navigation';
	import { cargarFicha, esNivel, leerJson, type Ficha } from '#lib/datos.ts';
	import { NOMBRE_SITIO } from '#lib/sitio.ts';
	import Mapa from '#lib/mapa/Mapa.svelte';
	import Leyenda from '#lib/mapa/Leyenda.svelte';
	import PanelTerritorio from '#lib/mapa/PanelTerritorio.svelte';
	import {
		avisoNivel,
		clasesCuantiles,
		estadoDesdeUrl,
		ETIQUETA_NIVEL_MAPA,
		indicadoresDelTema,
		NIVELES_MAPA,
		nivelMasDetallado,
		TEMAS,
		urlDesdeEstado,
		ZOOM_SEGMENTOS,
		type EstadoMapa,
		type NivelMapa
	} from '#lib/mapa/estado.ts';

	let { data } = $props();

	interface ValoresNivel {
		nivel: string;
		indicadores: Record<string, Record<string, Record<string, number | null>>>;
		estimados: Record<string, Record<string, string[]>>;
	}

	// Valor inicial para el prerender; en el navegador se lee de la URL al montar.
	let estado = $state<EstadoMapa>(estadoDesdeUrl(new URLSearchParams(), untrack(() => data.indicadores)));
	let tema = $state<string>(TEMAS[0]);
	let montado = $state(false);
	let zoom = $state(6);
	let valoresNivel = $state<ValoresNivel | null>(null);
	let ficha = $state<Ficha | null>(null);
	let errorFicha = $state('');
	let mapa: ReturnType<typeof Mapa> | undefined = $state();
	let enfocarAlCargar = false;

	let indicador = $derived(data.indicadores.find((i) => i.codigo === estado.indicador) ?? data.indicadores[0]);
	let delTema = $derived(indicadoresDelTema(data.indicadores, tema));
	let aviso = $derived(indicador ? avisoNivel(indicador, estado.nivel) : null);
	let valores = $derived<Record<string, number | null>>(
		!aviso && valoresNivel?.nivel === estado.nivel ? (valoresNivel.indicadores[estado.indicador]?.[estado.periodo] ?? {}) : {}
	);
	let clases = $derived(clasesCuantiles(Object.values(valores).filter((v): v is number => v !== null)));
	let hayEstimados = $derived(!!valoresNivel?.estimados[estado.indicador]?.[estado.periodo]?.length);
	let fuente = $derived.by(() => {
		const f = data.fuentes.find((x) => x.id === indicador?.fuente_id);
		return f ? `${siglas(f.organismo)}, ${f.nombre}` : '';
	});
	let seleccionadoId = $derived(estado.territorio ? `INE-2023/${estado.territorio}` : null);
	let faltaZoom = $derived(estado.nivel === 'segmento' && zoom < ZOOM_SEGMENTOS);

	/** "Instituto Nacional de Estadística (INE)" -> "INE". */
	function siglas(organismo: string): string {
		return organismo.replace(/^.*\((\w+)\)$/, '$1');
	}

	onMount(() => {
		estado = estadoDesdeUrl(new URLSearchParams(location.search), data.indicadores);
		tema = indicador?.tema ?? TEMAS[0];
		enfocarAlCargar = !!estado.territorio;
		montado = true;
	});

	// Estado en la URL (AC-M5).
	$effect(() => {
		const url = urlDesdeEstado(estado);
		if (montado && url !== location.search) replaceState(url, {});
	});

	// Valores del nivel elegido.
	$effect(() => {
		const nivel = estado.nivel;
		if (!montado) return;
		leerJson<ValoresNivel>(`valores/${nivel}.json`).then((v) => {
			if (estado.nivel === nivel) valoresNivel = v;
		});
	});

	// Ficha del territorio seleccionado.
	$effect(() => {
		const t = estado.territorio;
		if (!montado) return;
		if (!t) {
			ficha = null;
			return;
		}
		const [nivel, codigo] = t.split('/');
		errorFicha = '';
		if (!esNivel(nivel)) return;
		cargarFicha(nivel, codigo)
			.then((f) => {
				if (estado.territorio !== t) return;
				ficha = f;
				if (enfocarAlCargar) mapa?.enfocar(f.bbox);
				enfocarAlCargar = false;
			})
			.catch(() => {
				errorFicha = 'No encontramos ese territorio.';
				ficha = null;
			});
	});

	function elegirTema(t: string) {
		tema = t;
		const primero = indicadoresDelTema(data.indicadores, t)[0];
		if (primero) elegirIndicador(primero.codigo);
	}

	function elegirIndicador(codigo: string) {
		const ind = data.indicadores.find((i) => i.codigo === codigo);
		if (!ind) return;
		estado.indicador = codigo;
		if (!ind.periodos.includes(estado.periodo)) estado.periodo = ind.periodos.at(-1) ?? '';
	}

	function elegirNivel(n: NivelMapa) {
		estado.nivel = n;
	}

	function seleccionar(id: string) {
		const [, nivel, codigo] = id.split('/');
		estado.territorio = `${nivel}/${codigo}`;
	}

	function hastaDonde(i: (typeof data.indicadores)[number]): string {
		const n = nivelMasDetallado(i);
		return n ? `hasta ${ETIQUETA_NIVEL_MAPA[n].toLowerCase()}` : 'sin datos en el mapa';
	}
</script>

<svelte:head>
	<title>Mapa · {NOMBRE_SITIO}</title>
</svelte:head>

{#snippet leyenda()}
	{#if indicador && !aviso}
		<Leyenda
			titulo={indicador.nombre}
			unidad={indicador.unidad}
			{clases}
			{fuente}
			periodo={estado.periodo}
			{hayEstimados}
		/>
	{/if}
{/snippet}

<div class="pantalla">
	<aside class="opciones" aria-label="Opciones del mapa">
		<h1>Mapa</h1>

		<fieldset class="temas">
			<legend>Tema</legend>
			<div class="chips">
				{#each TEMAS as t (t)}
					<label class="chip" class:activo={tema === t}>
						<input type="radio" name="tema" value={t} checked={tema === t} onchange={() => elegirTema(t)} />
						{t}
					</label>
				{/each}
			</div>
		</fieldset>

		<fieldset>
			<legend>Indicador</legend>
			{#if delTema.length === 0}
				<p class="aviso">Todavía no hay fuentes cargadas para este tema.</p>
			{:else}
				<label class="visualmente-oculto" for="indicador-movil">Indicador</label>
				<select
					id="indicador-movil"
					class="solo-movil"
					value={estado.indicador}
					onchange={(e) => elegirIndicador(e.currentTarget.value)}
				>
					{#each delTema as i (i.codigo)}<option value={i.codigo}>{i.nombre}</option>{/each}
				</select>
				<div class="solo-escritorio lista-indicadores">
					{#each delTema as i (i.codigo)}
						<label class="indicador" class:activo={estado.indicador === i.codigo}>
							<input
								type="radio"
								name="indicador"
								value={i.codigo}
								checked={estado.indicador === i.codigo}
								onchange={() => elegirIndicador(i.codigo)}
							/>
							<span>
								<span class="nombre">{i.nombre}</span>
								<span class="detalle">
									{siglas(data.fuentes.find((f) => f.id === i.fuente_id)?.organismo ?? '')} · {hastaDonde(i)}
								</span>
							</span>
						</label>
					{/each}
				</div>
			{/if}
		</fieldset>

		<fieldset>
			<legend>Nivel territorial</legend>
			<div class="segmentado">
				{#each NIVELES_MAPA as n (n)}
					<label class:activo={estado.nivel === n}>
						<input type="radio" name="nivel" value={n} checked={estado.nivel === n} onchange={() => elegirNivel(n)} />
						{ETIQUETA_NIVEL_MAPA[n]}
					</label>
				{/each}
			</div>
		</fieldset>

		{#if indicador}
			<div class="campo">
				<label for="periodo">Período</label>
				<select id="periodo" bind:value={estado.periodo}>
					{#each indicador.periodos as p (p)}<option value={p}>{p}</option>{/each}
				</select>
			</div>
		{/if}

		<!-- La leyenda va fuera del mapa para no tapar territorios. -->
		<div class="solo-escritorio">{@render leyenda()}</div>
	</aside>

	<section class="centro" aria-label="Mapa interactivo">
		<Mapa
			bind:this={mapa}
			nivel={estado.nivel}
			{valores}
			{clases}
			seleccionado={seleccionadoId}
			onseleccionar={seleccionar}
			onzoom={(z) => (zoom = z)}
		/>

		<div class="avisos">
			{#if aviso}
				<div class="aviso" role="status">
					<p>{aviso.mensaje}</p>
					{#if aviso.alternativa}
						{@const alt = aviso.alternativa}
						<button type="button" onclick={() => elegirNivel(alt)}>
							Ver por {ETIQUETA_NIVEL_MAPA[alt].toLowerCase()}
						</button>
					{/if}
				</div>
			{:else if faltaZoom}
				<div class="aviso" role="status"><p>Acercá el mapa para ver los segmentos.</p></div>
			{/if}
		</div>

	</section>

	<div class="solo-movil leyenda-movil">{@render leyenda()}</div>

	<aside class="territorio" class:abierto={!!ficha} aria-label="Territorio seleccionado">
		{#if ficha}
			<PanelTerritorio
				{ficha}
				indicador={estado.indicador}
				periodo={estado.periodo}
				oncerrar={() => (estado.territorio = null)}
			/>
		{:else if errorFicha}
			<p class="aviso">{errorFicha}</p>
		{:else}
			<p class="suave pista">Tocá un territorio en el mapa para ver sus datos.</p>
		{/if}
	</aside>
</div>

<style>
	.pantalla {
		display: grid;
		grid-template-columns: 290px minmax(0, 1fr) 330px;
		height: calc(100dvh - 72px);
		min-height: 560px;
		background: var(--fondo);
	}

	.opciones,
	.territorio {
		background: var(--tarjeta);
		overflow-y: auto;
		padding: var(--espacio-4);
	}

	.opciones {
		border-right: 1px solid var(--borde);
		display: grid;
		align-content: start;
		gap: var(--espacio-4);
	}

	.territorio {
		border-left: 1px solid var(--borde);
	}

	h1 {
		font-size: var(--texto-l);
		margin: 0;
	}

	fieldset {
		border: 0;
		margin: 0;
		padding: 0;
		min-width: 0;
	}

	legend,
	.campo label {
		font-weight: 600;
		font-size: var(--texto-s);
		margin-bottom: var(--espacio-2);
		padding: 0;
	}

	.campo {
		display: grid;
	}

	/* Radios ocultos dentro de su etiqueta (que es la que se ve). La etiqueta los contiene para
	   que no se salgan de la fila de chips con scroll y estiren la página (AC-G4). */
	.chip,
	.indicador,
	.segmentado label {
		position: relative;
	}

	input[type='radio'] {
		position: absolute;
		inset: 0;
		opacity: 0;
		width: 1px;
		height: 1px;
		margin: 0;
	}

	label:has(input:focus-visible) {
		outline: 3px solid var(--foco);
		outline-offset: 2px;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-2);
	}

	.chip {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
		padding: 0 var(--espacio-3);
		border: 1px solid var(--borde);
		border-radius: 999px;
		background: var(--tarjeta);
		cursor: pointer;
		white-space: nowrap;
		font-size: var(--texto-s);
	}

	.chip.activo,
	.segmentado label.activo {
		background: var(--primario);
		border-color: var(--primario);
		color: var(--sobre-primario);
	}

	.lista-indicadores {
		display: grid;
		gap: var(--espacio-1);
	}

	.indicador {
		display: flex;
		align-items: center;
		min-height: var(--toque-min);
		padding: var(--espacio-2) var(--espacio-3);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		cursor: pointer;
	}

	.indicador.activo {
		border-color: var(--primario);
		box-shadow: inset 4px 0 0 var(--primario);
		background: var(--azul-1);
	}

	.indicador .nombre {
		display: block;
		font-weight: 600;
	}

	.indicador .detalle {
		display: block;
		font-size: var(--texto-xs);
		color: var(--texto-suave);
	}

	.segmentado {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		overflow: hidden;
	}

	.segmentado label {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: var(--toque-min);
		cursor: pointer;
		font-size: var(--texto-s);
	}

	.segmentado label + label {
		border-left: 1px solid var(--borde);
	}

	select {
		min-height: var(--toque-min);
		width: 100%;
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		background: var(--tarjeta);
		padding: 0 var(--espacio-3);
		font: inherit;
		color: var(--texto);
	}

	.centro {
		position: relative;
		min-width: 0;
	}

	.avisos {
		position: absolute;
		top: var(--espacio-3);
		left: var(--espacio-3);
		right: 60px;
		z-index: 3;
		display: grid;
		justify-items: start;
		pointer-events: none;
	}

	.avisos .aviso {
		pointer-events: auto;
		max-width: 520px;
		box-shadow: var(--sombra);
	}

	.avisos p {
		margin: 0;
	}

	.avisos button {
		margin-top: var(--espacio-2);
		min-height: var(--toque-min);
		padding: 0 var(--espacio-3);
		border: 1px solid var(--aviso-borde);
		border-radius: var(--radio-s);
		background: var(--tarjeta);
		color: var(--aviso-texto);
		font: inherit;
		font-weight: 600;
		cursor: pointer;
	}


	.pista {
		margin: 0;
	}

	.solo-movil {
		display: none;
	}

	.leyenda-movil {
		padding: var(--espacio-3) var(--espacio-4);
	}

	@media (max-width: 900px) {
		.pantalla {
			grid-template-columns: minmax(0, 1fr);
			grid-template-rows: auto minmax(420px, 70dvh) auto;
			height: auto;
			min-height: 0;
		}

		.opciones {
			border-right: 0;
			border-bottom: 1px solid var(--borde);
			gap: var(--espacio-3);
			overflow: visible;
		}

		/* AC-M6: temas como fila horizontal de chips */
		.chips {
			flex-wrap: nowrap;
			overflow-x: auto;
			padding-bottom: var(--espacio-1);
		}

		.solo-movil {
			display: block;
		}

		.solo-escritorio {
			display: none;
		}


		/* AC-M6: panel del territorio como hoja inferior */
		.territorio {
			position: fixed;
			left: 0;
			right: 0;
			bottom: 0;
			z-index: 30;
			max-height: 45dvh;
			border-left: 0;
			border-top: 1px solid var(--borde);
			border-radius: var(--radio-l) var(--radio-l) 0 0;
			box-shadow: 0 -4px 16px rgb(27 36 48 / 0.15);
			display: none;
		}

		.territorio.abierto {
			display: block;
		}
	}
</style>
