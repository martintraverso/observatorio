<script lang="ts">
	// Pantalla Mapa (M6): tema → indicador → nivel → período; coropleta; panel del territorio.
	import { onMount, tick, untrack } from 'svelte';
	import { replaceState } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { cargarEducacion, cargarFicha, esNivel, hrefFicha, leerJson, unirEducacion, type Ficha } from '#lib/datos.ts';
	import { NOMBRE_SITIO } from '#lib/sitio.ts';
	import Mapa from '#lib/mapa/Mapa.svelte';
	import Leyenda from '#lib/mapa/Leyenda.svelte';
	import PanelTerritorio from '#lib/mapa/PanelTerritorio.svelte';
	import ComparacionRegional from '#lib/mapa/ComparacionRegional.svelte';
	import {
		avisoSinMapa,
		clasesCuantiles,
		detalleLista,
		encuadreNivel,
		estadoDesdeUrl,
		etiquetaLista,
		etiquetaPeriodo,
		familiaDe,
		verPor,
		todasLas,
		type OpcionVerPor,
		formaSelectorNivel,
		fuenteCorta,
		gruposDelTema,
		indicadorInicialDelTema,
		indicadoresDelGrupo,
		minuscula,
		nivelAlCambiar,
		nivelesOfrecidos,
		opcionNivel,
		territorioAlCambiarNivel,
		totalDelPais,
		TEMAS,
		urlDesdeEstado,
		zoomMinimo,
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
	let estado = $state<EstadoMapa>(estadoDesdeUrl(new URLSearchParams(), untrack(() => data.indicadores), untrack(() => data.catalogo)));
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
	// AC-E26 (#214): un tema con niveles educativos (Educación) filtra la lista por el nivel elegido
	let grupo = $state<string | null>(null);
	let grupos = $derived(gruposDelTema(data.indicadores, tema));
	let delTema = $derived(indicadoresDelGrupo(data.indicadores, tema, grupos.length ? grupo : null));
	// AC-N9: el mapa nunca avisa «no se publica por…»; solo queda el aviso del indicador sin niveles en el mapa (AC-N6).
	let aviso = $derived(indicador ? avisoSinMapa(indicador, data.catalogo) : null);
	let valores = $derived<Record<string, number | null>>(
		!aviso && valoresNivel?.nivel === estado.nivel ? (valoresNivel.indicadores[estado.indicador]?.[estado.periodo] ?? {}) : {}
	);
	let clases = $derived(clasesCuantiles(Object.values(valores).filter((v): v is number => v !== null)));
	let hayEstimados = $derived(!!valoresNivel?.estimados[estado.indicador]?.[estado.periodo]?.length);
	let fuente = $derived.by(() => {
		const f = data.fuentes.find((x) => x.id === indicador?.fuente_id);
		return f ? fuenteCorta(f) : '';
	});
	// AC-N4: los niveles del indicador elegido (con datos y dibujables); AC-N6: lista, texto fijo u oculto.
	let niveles = $derived(nivelesOfrecidos(indicador, data.catalogo));
	let formaNivel = $derived(formaSelectorNivel(niveles));
	// AC-N11: lo que se anuncia (región viva cortés) cuando el nivel cambia solo al cambiar de indicador (AC-N7).
	let anuncioNivel = $state('');
	// Total del país publicado por la fuente (valores/pais.json), para la nota del panel (F2.8b).
	let valoresPais = $state<ValoresNivel | null>(null);
	let totalPais = $derived(totalDelPais(valoresPais, estado.indicador, estado.periodo));
	let seleccionadoId = $derived(estado.territorio ? `INE-2023/${estado.territorio}` : null);
	// AC-V13: en celular y tableta los controles van en una hoja que se abre desde una barra compacta.
	let opcionesAbiertas = $state(false);
	let resumenOpciones = $derived(
		[
			indicador?.nombre ?? tema,
			formaNivel === 'oculto' ? null : opcionNivel(data.catalogo, estado.nivel).etiqueta,
			indicador ? etiquetaPeriodo(estado.periodo) : null
		]
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
	// Un nivel que se dibuja desde cierto zoom (los segmentos, AC-N1) y el mapa todavía no llegó.
	let zoomNivel = $derived(zoomMinimo(data.catalogo, estado.nivel));
	let faltaZoom = $derived(zoomNivel > 0 && zoom < zoomNivel);

	/** "Instituto Nacional de Estadística (INE)" -> "INE". */
	function siglas(organismo: string): string {
		return organismo.replace(/^.*\((\w+)\)$/, '$1');
	}

	onMount(() => {
		estado = estadoDesdeUrl(new URLSearchParams(location.search), data.indicadores, data.catalogo);
		tema = indicador?.tema ?? TEMAS[0];
		grupo = indicador?.grupo || null;
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
				// Nivel sin archivo de valores (no debería pasar: solo se ofrecen niveles con datos, AC-N4).
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
		// #227: con un indicador de educación, el panel necesita la educación de la ficha (va aparte)
		const conEdu = !!estado.indicador?.startsWith('edu_');
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
			.then(async (f) => {
				const parte = conEdu && f.educacion ? await cargarEducacion(nivel, codigo).catch(() => null) : null;
				if (estado.territorio !== t) return;
				ficha = unirEducacion(f, parte);
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
		// el indicador con que abre el tema (Educación: D3, la tasa de promoción en primaria pública) y su nivel educativo
		const inicial = indicadorInicialDelTema(data.indicadores, t);
		grupo = inicial?.grupo || null;
		if (inicial) {
			elegirIndicador(inicial.codigo);
			// AC-E26: un tema abre en el último período de su indicador (no en el del tema anterior)
			estado.periodo = inicial.periodos.at(-1) ?? estado.periodo;
		}
	}

	/** AC-E26: al elegir un nivel educativo, el primer indicador del nivel (su total). */
	function elegirGrupo(g: string) {
		grupo = g;
		const primero = indicadoresDelGrupo(data.indicadores, tema, g)[0];
		if (primero) elegirIndicador(primero.codigo);
	}

	function elegirIndicador(codigo: string) {
		const ind = data.indicadores.find((i) => i.codigo === codigo);
		if (!ind) return;
		estado.indicador = codigo;
		if (!ind.periodos.includes(estado.periodo)) estado.periodo = ind.periodos.at(-1) ?? '';
		// AC-N7: si el nivel actual no se ofrece para este indicador, al más cercano que lo contiene (o al más grueso),
		// con el encuadre y la regla de selección de siempre (AC-V7, AC-V8), sin aviso; se anuncia (AC-N11).
		const nuevo = nivelAlCambiar(estado.nivel, nivelesOfrecidos(ind, data.catalogo), data.catalogo);
		if (nuevo && nuevo !== estado.nivel) {
			elegirNivel(nuevo);
			anunciarNivel(`Nivel: ${opcionNivel(data.catalogo, nuevo).etiqueta}`);
		}
	}

	/**
	 * AC-N11: se vacía y se vuelve a escribir un momento después, para que un segundo cambio al mismo nivel (mismo
	 * texto) también se anuncie: el navegador tiene que ver la región vacía en un cuadro antes del texto nuevo.
	 */
	let esperaAnuncio: ReturnType<typeof setTimeout> | undefined;
	function anunciarNivel(texto: string) {
		anuncioNivel = '';
		clearTimeout(esperaAnuncio);
		esperaAnuncio = setTimeout(() => (anuncioNivel = texto), 100);
	}

	/** La ficha cargada, solo si es la del territorio elegido (mientras carga otra, la anterior no vale). */
	function fichaVigente(): Ficha | null {
		return ficha && estado.territorio && ficha.id === `INE-2023/${estado.territorio}` ? ficha : null;
	}

	/** Departamento del territorio elegido, si hay uno. */
	function deptoElegido(): string | null {
		const f = fichaVigente();
		if (f?.depto) return f.depto;
		// Sin la ficha: el departamento que se sabe por el código o por el ámbito (lo de Montevideo, 01).
		const t = estado.territorio ? territorioAlCambiarNivel(estado.territorio, 'departamento', data.catalogo) : null;
		return t ? t.split('/')[1] : null;
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
		// El padre de ese nivel según la ficha, para cualquier nivel del catálogo (M11.3).
		const padre = fichaVigente()?.padres.find((p) => p.nivel === n);
		if (padre) return `${padre.nivel}/${padre.codigo}`;
		// Sin la ficha todavía: el departamento por el código INE (sección, segmento) o por el ámbito (Montevideo).
		return territorioAlCambiarNivel(t, n, data.catalogo);
	}

	/**
	 * Al cambiar de nivel el mapa se encuadra donde ese nivel tiene sentido (AC-V7), según el catálogo: Montevideo
	 * para los niveles solo de Montevideo (municipio, barrio); el país para los que no están dentro de un
	 * departamento; el departamento elegido para los demás (los segmentos, con el zoom desde el que se dibujan).
	 */
	function elegirNivel(n: NivelMapa) {
		const depto = deptoElegido();
		estado.nivel = n;
		estado.territorio = territorioEnNivel(n);
		// AC-V7 por el catálogo (M11.3): Montevideo, el país o el departamento elegido, sin código por nivel
		const encuadre = encuadreNivel(data.catalogo, n);
		if (encuadre === 'montevideo') enfocarDepto('01');
		else if (encuadre === 'pais') mapa?.enfocarPais();
		else if (depto) enfocarDepto(depto, zoomMinimo(data.catalogo, n));
	}

	function seleccionar(id: string) {
		const [, nivel, codigo] = id.split('/');
		estado.territorio = `${nivel}/${codigo}`;
	}

	// AC-V38 (#250): los filtros «Ver por» de la familia elegida, con los cortes que tienen datos en el nivel y período
	let filtros = $derived(
		verPor(data.indicadores, indicador, (codigo) => {
			if (valoresNivel?.nivel !== estado.nivel) return true; // todavía cargando: no se esconde nada
			return Object.values(valoresNivel.indicadores[codigo]?.[estado.periodo] ?? {}).some((v) => v !== null);
		})
	);

	/** AC-V39: elegir un corte; si la combinación no existía, las otras dimensiones vuelven a «Todas» y se anuncia. */
	function elegirApertura(o: OpcionVerPor) {
		elegirIndicador(o.codigo);
		if (o.reinicia.length) anunciarNivel(o.reinicia.map((d) => `${d}: ${todasLas(d)}`).join(', '));
	}

	// AC-V41 (#249): hay indicadores de este tema y nivel educativo que no van al mapa
	let hayFueraDelMapa = $derived(!!data.fueraDelMapa[`${tema}|${grupos.length ? (grupo ?? '') : ''}`]);
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
			calculado={indicador.es_derivado ? siglas(data.fuentes.find((f) => f.id === indicador?.fuente_id)?.organismo ?? '') : null}
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

		{#if grupos.length}
			<fieldset class="temas">
				<legend>Nivel educativo</legend>
				<div class="chips">
					{#each grupos as g (g)}
						<label class="chip" class:activo={grupo === g}>
							<input
								type="radio"
								name="grupo"
								value={g}
								checked={grupo === g}
								onchange={() => elegirGrupo(g)}
								onfocus={(e) => e.currentTarget.closest('label')?.scrollIntoView({ inline: 'center', block: 'nearest' })}
							/>
							{g}
						</label>
					{/each}
				</div>
			</fieldset>
		{/if}

		<fieldset>
			<legend>Indicador</legend>
			{#if delTema.length === 0}
				<p class="info">Todavía no hay fuentes cargadas para este tema.</p>
			{:else}
				<label class="visualmente-oculto" for="indicador-movil">Indicador</label>
				<select
					id="indicador-movil"
					class="solo-movil"
					value={familiaDe(indicador)}
					onchange={(e) => elegirIndicador(e.currentTarget.value)}
				>
					{#each delTema as i (i.codigo)}<option value={i.codigo}>{etiquetaLista(i)}</option>{/each}
				</select>
				<div class="solo-escritorio lista-indicadores">
					{#each delTema as i (i.codigo)}
						<label class="indicador" class:activo={familiaDe(indicador) === i.codigo}>
							<input
								type="radio"
								name="indicador"
								value={i.codigo}
								checked={familiaDe(indicador) === i.codigo}
								onchange={() => estado.indicador !== i.codigo && elegirIndicador(i.codigo)}
								onclick={() => estado.indicador !== i.codigo && elegirIndicador(i.codigo)}
							/>
							<span>
								<span class="nombre">{etiquetaLista(i)}</span>
								<span class="detalle">{detalleLista(i, data.catalogo)}</span>
							</span>
						</label>
					{/each}
				</div>
			{/if}
			{#if hayFueraDelMapa && delTema.length}
				<!-- AC-V41 (#249): lo que no se dibuja sigue en el catálogo de educación o en la ficha de Uruguay -->
				<p class="info fuera-del-mapa">
					{#if tema === 'Educación'}
						Otros indicadores de {minuscula(grupo ?? 'educación')} no se dibujan en el mapa: están en el
						<a href={resolve('/educacion')}>catálogo de educación</a>.
					{:else}
						Otros indicadores de {minuscula(tema)} no se dibujan en el mapa: están en la
						<a href={hrefFicha({ nivel: 'pais', codigo: 'UY' })}>ficha de Uruguay</a>.
					{/if}
				</p>
			{/if}
		</fieldset>

		{#if filtros.length}
			<!-- AC-V38/AC-V39 (#250): las aperturas de la familia elegida, una fila de opciones por dimensión -->
			<div class="ver-por" role="group" aria-labelledby="titulo-ver-por">
				<p class="titulo-ver-por" id="titulo-ver-por">Ver por</p>
				{#each filtros as f (f.dimension)}
					<fieldset class="segmentado">
						<legend>{f.dimension}</legend>
						<div class="segmentos">
							{#each f.opciones as o (o.etiqueta)}
								<label class="segmento" class:activo={o.activo}>
									<input type="radio" name="ver-por-{f.dimension}" value={o.codigo} checked={o.activo} onchange={() => elegirApertura(o)} />
									{o.etiqueta}
								</label>
							{/each}
						</div>
					</fieldset>
				{/each}
			</div>
		{/if}

		{#if formaNivel === 'lista'}
			<fieldset>
				<legend>Nivel territorial</legend>
				<!-- Lista vertical: entra cualquier cantidad de niveles sin cortar ninguno (AC-V1, AC-N10). -->
				<div class="lista-niveles">
					{#each niveles as n (n)}
						{@const opcion = opcionNivel(data.catalogo, n)}
						<label class="nivel" class:activo={estado.nivel === n}>
							<input type="radio" name="nivel" value={n} checked={estado.nivel === n} onchange={() => elegirNivel(n)} />
							<span class="nombre">{opcion.etiqueta}</span>
							{#if opcion.ayuda}<span class="ayuda">{opcion.ayuda}</span>{/if}
						</label>
					{/each}
				</div>
			</fieldset>
		{:else if formaNivel === 'texto'}
			<!-- AC-N6: con un solo nivel, texto fijo en lugar de un control de una sola opción -->
			{@const opcion = opcionNivel(data.catalogo, niveles[0])}
			<p class="nivel-unico">
				<span class="etiqueta-campo">Nivel:</span>
				{opcion.etiqueta}{#if opcion.ayuda}<span class="ayuda"> · {opcion.ayuda}</span>{/if}
			</p>
		{/if}
		<!-- AC-N11: el cambio automático de nivel (AC-N7) se anuncia sin mover el foco -->
		<p class="visualmente-oculto" aria-live="polite">{anuncioNivel}</p>

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
			catalogo={data.catalogo}
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
				<!-- con la comparación regional, solo el aviso es región viva: la figura no se relee entera al cambiar de período -->
				<div class="info" role={aviso.regional ? undefined : 'status'}>
					<p role={aviso.regional ? 'status' : undefined}>{aviso.mensaje}</p>
					{#if aviso.regional && indicador}
						<!-- AC-I20: en lugar del coroplético, la comparación entre regiones -->
						<ComparacionRegional {indicador} periodo={estado.periodo} />
					{/if}
				</div>
			{:else if faltaZoom}
				<div class="info" role="status">
					<p>Acercá el mapa para ver los segmentos, o elegí un departamento:</p>
					<label class="visualmente-oculto" for="elegir-depto">Elegí un departamento</label>
					<select
						id="elegir-depto"
						onchange={(e) => {
							if (e.currentTarget.value) enfocarDepto(e.currentTarget.value, zoomNivel);
						}}
					>
						<option value="">Elegí un departamento</option>
						{#each data.departamentos as d (d.codigo)}<option value={d.codigo}>{d.nombre}</option>{/each}
					</select>
				</div>
			{/if}
		</div>

		{#if !hayPanel && !aviso?.regional}
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

	/* AC-V40 (#250): «Ver por», con los tokens del sistema; ≥ 40 px en el panel de escritorio, ≥ 44 px en celular */
	.ver-por {
		display: grid;
		gap: var(--espacio-2);
		margin-top: var(--espacio-3);
	}

	.titulo-ver-por {
		margin: 0;
		font-weight: 600;
	}

	.segmentado {
		margin: 0;
		padding: 0;
		border: 0;
		min-width: 0;
	}

	.segmentado legend {
		font-size: var(--texto-s);
		color: var(--texto-suave);
		padding: 0;
		margin-bottom: var(--espacio-1);
	}

	.segmentos {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-1);
	}

	.segmento {
		position: relative;
		display: inline-flex;
		align-items: center;
		min-height: 40px;
		padding: 0 var(--espacio-3);
		border: 1px solid var(--borde);
		border-radius: var(--radio-s);
		background: var(--tarjeta);
		cursor: pointer;
		white-space: nowrap;
		font-size: var(--texto-s);
	}

	.segmento.activo {
		background: var(--primario);
		border-color: var(--primario);
		color: var(--sobre-primario);
	}

	.segmento:has(input:focus-visible) {
		outline: 3px solid var(--foco);
		outline-offset: 2px;
	}

	@media (max-width: 900px) {
		.segmento {
			min-height: var(--toque-min);
		}
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

	.nivel-unico {
		margin: 0;
	}

	.nivel-unico .etiqueta-campo {
		font-weight: 600;
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
