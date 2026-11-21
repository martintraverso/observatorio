<script lang="ts">
	// Pantalla Mapa (M6): tema → indicador → nivel → período; coropleta; panel del territorio.
	import { onMount, tick, untrack } from 'svelte';
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
		etiquetaPeriodo,
		fuenteCorta,
		indicadoresDelTema,
		minuscula,
		nivelesConDatos,
		nivelMasDetallado,
		OPCION_NIVEL_MAPA,
		totalDelPais,
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
	// Ancho de la leyenda superpuesta al mapa (0 en móvil, donde va debajo).
	let anchoLeyenda = $state(0);

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
		return f ? fuenteCorta(f) : '';
	});
	let niveles = $derived(nivelesConDatos(data.indicadores));
	// Total del país publicado por la fuente (valores/pais.json), para la nota del panel (F2.8b).
	let valoresPais = $state<ValoresNivel | null>(null);
	let totalPais = $derived(totalDelPais(valoresPais, estado.indicador, estado.periodo));
	let seleccionadoId = $derived(estado.territorio ? `INE-2023/${estado.territorio}` : null);
	// AC-V13: en celular y tableta los controles van en una hoja que se abre desde una barra compacta.
	let opcionesAbiertas = $state(false);
	let resumenOpciones = $derived(
		[indicador?.nombre ?? tema, OPCION_NIVEL_MAPA[estado.nivel].etiqueta, indicador ? etiquetaPeriodo(estado.periodo) : null]
			.filter(Boolean)
			.join(' · ')
	);
	let barraOpciones: HTMLButtonElement | undefined = $state();
	let controles: HTMLDivElement | undefined = $state();

	async function abrirOpciones() {
		opcionesAbiertas = true;
		await tick();
		// el foco va a lo elegido (el tema), no al botón «Listo» de la cabecera
		controles?.querySelector<HTMLElement>('fieldset input:checked, select')?.focus();
	}

	function cerrarOpciones() {
		opcionesAbiertas = false;
		barraOpciones?.focus();
	}

	// AC-V10: sin territorio elegido no hay panel derecho; el mapa usa ese ancho y la pista va sobre el mapa.
	let hayPanel = $derived(!!estado.territorio);
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
		leerJson<ValoresNivel>(`valores/${nivel}.json`)
			.then((v) => {
				if (estado.nivel === nivel) valoresNivel = v;
			})
			.catch(() => {
				// Nivel sin valores publicados (p. ej. llegado por URL): el aviso de AC-M2 lo explica.
				if (estado.nivel === nivel) valoresNivel = null;
			});
	});

	$effect(() => {
		if (!montado || !indicador?.niveles.includes('pais') || valoresPais) return;
		leerJson<ValoresNivel>('valores/pais.json')
			.then((v) => (valoresPais = v))
			.catch(() => (valoresPais = null));
	});

	// Ficha del territorio seleccionado.
	$effect(() => {
		const t = estado.territorio;
		if (!montado) return;
		if (!t) {
			ficha = null;
			errorFicha = '';
			return;
		}
		const [nivel, codigo] = t.split('/');
		errorFicha = '';
		if (!esNivel(nivel)) {
			errorFicha = 'No encontramos ese territorio.';
			return;
		}
		cargarFicha(nivel, codigo)
			.then((f) => {
				if (estado.territorio !== t) return;
				ficha = f;
				// las regiones (F3.2) no tienen geometría: no hay dónde encuadrar
				if (enfocarAlCargar && f.bbox) mapa?.enfocar(f.bbox);
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

	/** La ficha cargada, solo si es la del territorio elegido (mientras carga otra, la anterior no vale). */
	function fichaVigente(): Ficha | null {
		return ficha && estado.territorio && ficha.id === `INE-2023/${estado.territorio}` ? ficha : null;
	}

	/** Departamento del territorio elegido, si hay uno. */
	function deptoElegido(): string | null {
		const f = fichaVigente();
		if (f?.depto) return f.depto;
		const [nivel, codigo] = estado.territorio?.split('/') ?? [];
		if (nivel === 'departamento' || nivel === 'seccion' || nivel === 'segmento') return codigo.slice(0, 2);
		return null;
	}

	function enfocarDepto(codigo: string, zoomMinimo = 0) {
		const d = data.departamentos.find((x) => x.codigo === codigo);
		if (d) mapa?.enfocar(d.bbox, zoomMinimo);
	}

	/**
	 * Regla de selección al cambiar de nivel (AC-V8, docs/SYSTEM.md §8): el panel nunca muestra un territorio
	 * de otro nivel. Si el elegido es de ese nivel, se mantiene; si uno de sus padres lo es (ir a un nivel más
	 * grueso), se elige ese padre; si no (ir a uno más fino), el panel se vacía y el mapa queda encuadrado en
	 * el departamento.
	 */
	function territorioEnNivel(n: NivelMapa): string | null {
		const t = estado.territorio;
		if (!t || t.split('/')[0] === n) return t;
		const padre = fichaVigente()?.padres.find((p) => p.nivel === n);
		if (padre) return `${padre.nivel}/${padre.codigo}`;
		// Sin la ficha todavía: las secciones y los segmentos empiezan con el código de su departamento.
		const [nivel, codigo] = t.split('/');
		if (n === 'departamento' && (nivel === 'seccion' || nivel === 'segmento')) return `departamento/${codigo.slice(0, 2)}`;
		return null;
	}

	/**
	 * Al cambiar de nivel el mapa se encuadra donde ese nivel tiene sentido (AC-V7): Montevideo para los
	 * municipios; el departamento elegido para secciones y segmentos (los segmentos, con el zoom desde el
	 * que se dibujan); el país para departamentos.
	 */
	function elegirNivel(n: NivelMapa) {
		const depto = deptoElegido();
		estado.nivel = n;
		estado.territorio = territorioEnNivel(n);
		if (n === 'municipio_mvd') enfocarDepto('01');
		else if (n === 'departamento') mapa?.enfocarPais();
		else if (depto) enfocarDepto(depto, n === 'segmento' ? ZOOM_SEGMENTOS : 0);
	}

	function seleccionar(id: string) {
		const [, nivel, codigo] = id.split('/');
		estado.territorio = `${nivel}/${codigo}`;
	}

	function hastaDonde(i: (typeof data.indicadores)[number]): string {
		const n = nivelMasDetallado(i);
		return n ? `hasta ${minuscula(ETIQUETA_NIVEL_MAPA[n])}` : 'sin datos en el mapa';
	}
</script>

<svelte:window
	onkeydown={(e) => {
		// solo si el foco está en la hoja: Escape en el buscador u otro lado hace lo suyo
		if (e.key === 'Escape' && opcionesAbiertas && controles?.contains(document.activeElement)) cerrarOpciones();
	}}
/>

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
			periodo={etiquetaPeriodo(estado.periodo)}
			{hayEstimados}
		/>
	{/if}
{/snippet}

<div class="pantalla" class:con-panel={hayPanel}>
	<aside class="opciones" aria-label="Opciones del mapa">
		<h1>Mapa</h1>

		<!-- Celular y tableta: un resumen de lo elegido; abre los controles en una hoja (AC-V13). -->
		<button
			type="button"
			class="barra-opciones"
			bind:this={barraOpciones}
			aria-expanded={opcionesAbiertas}
			aria-controls="controles-mapa"
			onclick={abrirOpciones}
		>
			<span class="resumen">{resumenOpciones}</span>
			<span class="cambiar">Cambiar</span>
		</button>

		<div
			id="controles-mapa"
			class="controles"
			class:abiertas={opcionesAbiertas}
			bind:this={controles}
			role="group"
			aria-label="Opciones del mapa"
		>
		<div class="cabecera-hoja">
			<span>Opciones del mapa</span>
			<button type="button" class="boton-listo" onclick={cerrarOpciones}>Listo</button>
		</div>

		<fieldset class="temas">
			<legend>Tema</legend>
			<div class="chips">
				{#each TEMAS as t (t)}
					<label class="chip" class:activo={tema === t}>
						<input
							type="radio"
							name="tema"
							value={t}
							checked={tema === t}
							onchange={() => elegirTema(t)}
							onfocus={(e) => e.currentTarget.closest('label')?.scrollIntoView({ inline: 'center', block: 'nearest' })}
						/>
						{t}
					</label>
				{/each}
			</div>
		</fieldset>

		<fieldset>
			<legend>Indicador</legend>
			{#if delTema.length === 0}
				<p class="info">Todavía no hay fuentes cargadas para este tema.</p>
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
			<!-- Lista vertical: entra cualquier cantidad de niveles sin cortar ninguno (AC-V1). -->
			<div class="lista-niveles">
				{#each niveles as n (n)}
					{@const opcion = OPCION_NIVEL_MAPA[n]}
					<label class="nivel" class:activo={estado.nivel === n}>
						<input type="radio" name="nivel" value={n} checked={estado.nivel === n} onchange={() => elegirNivel(n)} />
						<span class="nombre">{opcion.etiqueta}</span>
						{#if opcion.ayuda}<span class="ayuda">{opcion.ayuda}</span>{/if}
					</label>
				{/each}
			</div>
		</fieldset>

		{#if indicador}
			<div class="campo">
				<label for="periodo">Período</label>
				<select id="periodo" bind:value={estado.periodo}>
					{#each indicador.periodos as p (p)}<option value={p}>{etiquetaPeriodo(p)}</option>{/each}
				</select>
			</div>
		{/if}
		</div>
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
			reservaIzquierda={anchoLeyenda}
			departamentos={data.departamentos}
		/>

		<div class="avisos">
			{#if aviso}
				<div class="info" role="status">
					<p>{aviso.mensaje}</p>
					{#if aviso.disponibles.length}
						<div class="disponibles">
							{#each aviso.disponibles as alt, i (alt)}
								{#if i > 0}<span aria-hidden="true">·</span>{/if}
								<button type="button" onclick={() => elegirNivel(alt)}>{minuscula(OPCION_NIVEL_MAPA[alt].etiqueta)}</button>
							{/each}
						</div>
					{/if}
				</div>
			{:else if faltaZoom}
				<div class="info" role="status">
					<p>Acercá el mapa para ver los segmentos, o elegí un departamento:</p>
					<label class="visualmente-oculto" for="elegir-depto">Elegí un departamento</label>
					<select
						id="elegir-depto"
						onchange={(e) => {
							if (e.currentTarget.value) enfocarDepto(e.currentTarget.value, ZOOM_SEGMENTOS);
						}}
					>
						<option value="">Elegí un departamento</option>
						{#each data.departamentos as d (d.codigo)}<option value={d.codigo}>{d.nombre}</option>{/each}
					</select>
				</div>
			{/if}
		</div>

		{#if !hayPanel}
			<p class="solo-escritorio pista-mapa">Tocá un territorio en el mapa para ver sus datos.</p>
		{/if}

		<!-- En escritorio la leyenda va sobre el mapa, abajo a la izquierda, siempre a la vista (AC-V4). -->
		<div class="solo-escritorio leyenda-sobre-mapa" bind:clientWidth={anchoLeyenda}>{@render leyenda()}</div>
	</section>

	<div class="solo-movil leyenda-movil">{@render leyenda()}</div>

	{#if hayPanel}
	<aside class="territorio" class:abierto={!!ficha || !!errorFicha} aria-label="Territorio seleccionado">
		{#if ficha}
			<PanelTerritorio
				{ficha}
				indicador={estado.indicador}
				periodo={estado.periodo}
				{totalPais}
				oncerrar={() => (estado.territorio = null)}
			/>
		{:else if errorFicha}
			<div class="error error-ficha" role="alert">
				<p>{errorFicha}</p>
				<button type="button" class="boton" onclick={() => (estado.territorio = null)}>Cerrar</button>
			</div>
		{:else}
			<p class="suave pista" role="status">Cargando el territorio…</p>
		{/if}
	</aside>
	{/if}
</div>

<style>
	.pantalla {
		display: grid;
		grid-template-columns: 290px minmax(0, 1fr);
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
		/* el espacio de la barra de scroll queda reservado: cambiar de tema o nivel no mueve nada (AC-V3) */
		scrollbar-gutter: stable;
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
	.nivel {
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

	.chip.activo {
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

	.indicador.activo,
	.nivel.activo {
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

	/* En escritorio los controles se ven siempre: sin barra ni cabecera de hoja. */
	.controles {
		display: grid;
		align-content: start;
		gap: var(--espacio-4);
	}

	.barra-opciones,
	.cabecera-hoja {
		display: none;
	}

	.lista-niveles {
		display: grid;
		gap: var(--espacio-1);
	}

	.nivel {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--espacio-2);
		min-height: var(--toque-min);
		padding: 0 var(--espacio-3);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		cursor: pointer;
		white-space: nowrap;
	}

	.nivel .nombre {
		font-weight: 600;
		font-size: var(--texto-s);
	}

	.nivel .ayuda {
		font-size: var(--texto-xs);
		color: var(--texto-suave);
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

	.avisos .info {
		pointer-events: auto;
		max-width: 520px;
		box-shadow: var(--sombra);
	}

	.avisos p {
		margin: 0;
	}

	.leyenda-sobre-mapa {
		position: absolute;
		left: var(--espacio-3);
		bottom: var(--espacio-6);
		z-index: 3;
		width: min(240px, calc(100% - 2 * var(--espacio-3)));
		box-shadow: var(--sombra);
		border-radius: var(--radio-m);
	}

	.avisos select {
		margin-top: var(--espacio-2);
		width: auto;
		min-width: 220px;
	}

	.disponibles {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--espacio-2);
	}

	.avisos button {
		margin-top: var(--espacio-2);
		min-height: var(--toque-min);
		padding: 0 var(--espacio-3);
		/* borde con contraste ≥ 3:1 sobre el aviso (WCAG 1.4.11) */
		border: 1px solid var(--foco);
		border-radius: var(--radio-s);
		background: var(--tarjeta);
		color: var(--info-texto);
		font: inherit;
		font-weight: 600;
		cursor: pointer;
	}


	.pantalla.con-panel {
		grid-template-columns: 290px minmax(0, 1fr) 330px;
	}

	.pista {
		margin: 0;
	}

	.error-ficha {
		display: grid;
		gap: var(--espacio-2);
		justify-items: start;
	}

	.error-ficha p {
		margin: 0;
	}

	.pista-mapa {
		position: absolute;
		right: var(--espacio-3);
		bottom: var(--espacio-6);
		z-index: 3;
		margin: 0;
		max-width: 220px;
		padding: var(--espacio-2) var(--espacio-3);
		background: var(--tarjeta);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		box-shadow: var(--sombra);
		font-size: var(--texto-s);
		color: var(--texto-suave);
		pointer-events: none;
	}

	.solo-movil {
		display: none;
	}

	.leyenda-movil {
		padding: var(--espacio-3) var(--espacio-4);
	}

	@media (max-width: 900px) {
		.pantalla,
		.pantalla.con-panel {
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

		/* AC-V13: barra compacta; los controles, en una hoja inferior que se abre desde ella */
		.barra-opciones {
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: var(--espacio-2);
			width: 100%;
			min-height: var(--toque-min);
			padding: var(--espacio-2) var(--espacio-3);
			border: 1px solid var(--borde);
			border-radius: var(--radio-m);
			background: var(--tarjeta);
			font: inherit;
			color: var(--texto);
			text-align: left;
			cursor: pointer;
		}

		.barra-opciones .resumen {
			font-weight: 600;
			font-size: var(--texto-s);
			min-width: 0;
		}

		.barra-opciones .cambiar {
			flex: none;
			color: var(--primario);
			font-weight: 600;
			font-size: var(--texto-s);
		}

		.controles {
			display: none;
		}

		.controles.abiertas {
			display: grid;
			position: fixed;
			left: 0;
			right: 0;
			bottom: 0;
			z-index: 40;
			max-height: 85dvh;
			overflow-y: auto;
			padding: var(--espacio-4);
			background: var(--tarjeta);
			border-top: 1px solid var(--borde);
			border-radius: var(--radio-l) var(--radio-l) 0 0;
			box-shadow: 0 -4px 16px rgb(27 36 48 / 0.15);
		}

		.cabecera-hoja {
			display: flex;
			align-items: center;
			justify-content: space-between;
			font-weight: 600;
		}

		.boton-listo {
			min-height: var(--toque-min);
			padding: 0 var(--espacio-4);
			border: 0;
			border-radius: var(--radio-m);
			background: var(--primario);
			color: var(--sobre-primario);
			font: inherit;
			font-weight: 600;
			cursor: pointer;
		}

		/* AC-M6: temas como fila horizontal de chips */
		/* AC-V15: fila desplazable sin barra visible; el borde derecho se desvanece para mostrar que hay más */
		.chips {
			flex-wrap: nowrap;
			overflow-x: auto;
			scrollbar-width: none;
			mask-image: linear-gradient(to right, #000 calc(100% - 48px), transparent);
			/* el último chip termina antes de la zona desvanecida; el enfocado se centra (onfocus) */
			padding-right: 56px;
			/* lugar para el anillo de foco, y el chip enfocado queda fuera del desvanecido */
			padding-block: 6px;
			padding-left: 6px;
			margin-left: -6px;
			scroll-padding-inline: 6px 56px;
		}

		.chips:has(:focus-visible) {
			mask-image: none;
		}

		.chips::-webkit-scrollbar {
			display: none;
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
