<script lang="ts">
	// Ficha de un territorio (M7, AC-F1…F7).
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import MiniMapa from '#lib/mapa/MiniMapa.svelte';
	import LocalizadorCerca from '#lib/mapa/LocalizadorCerca.svelte';
	import { descargarCsv } from '#lib/csv.ts';
	import { hrefFicha, NOMBRE_NIVEL, NIVELES, partesId, type Nivel, type Observacion, type Relacion } from '#lib/datos.ts';
	import { fecha, numero, publicado } from '#lib/formato.ts';
	import { NOMBRE_SITIO } from '#lib/sitio.ts';
	import {
		cita,
		consultaMapa,
		datosEnPadre,
		densidad,
		fuentesDeFicha,
		notaNoAditiva,
		observacionesDeSeccion,
		partes,
		SECCIONES_FICHA,
		SIN_FUENTES,
		valorDe,
		separarSeries
	} from '#lib/ficha/logica.ts';
	import SerieFicha from '#lib/ficha/SerieFicha.svelte';

	let { data } = $props();
	let f = $derived(data.ficha);

	const PERIODO = '2023';
	const PERTENECE: Partial<Record<string, string>> = {
		localidad: 'Pertenece a la localidad:',
		municipio_mvd: 'Pertenece al municipio:',
		pais: 'Pertenece al país:'
	};
	let contenidos = $derived(NIVELES.filter((n) => f.contenidos[n]?.length).map((n) => [n, f.contenidos[n]!] as const));
	let pestana = $state<Nivel | null>(null);
	let activa = $derived(pestana && f.contenidos[pestana]?.length ? pestana : (contenidos[0]?.[0] ?? null));
	let nota = $derived(notaNoAditiva(f));
	let url = $state('');
	let mensaje = $state('');
	let textoCita = $derived(url ? cita(f, url, new Date()) : '');

	onMount(() => {
		url = location.href;
	});

	const valor = (codigo: string) => f.observaciones.find((o) => o.indicador === codigo && o.periodo === PERIODO)?.valor ?? null;
	const ind = (o: Observacion) => f.indicadores[o.indicador];

	function fuenteDe(o: Observacion): string {
		const c = f.capturas[o.captura_id];
		const fu = c && f.fuentes[c.fuente_id];
		return fu ? `${fu.organismo.replace(/^.*\((\w+)\)$/, '$1')} · ${fu.nombre}` : o.captura_id;
	}

	// AC-V27: solo en las fichas de departamento; no es una observación (decisión del mantenedor, #111)
	let densidadDepto = $derived(f.nivel === 'departamento' ? densidad(valor('pob_total'), f.area_km2) : null);
	let fuenteKpi = $derived.by(() => {
		const o = f.observaciones.find((x) => x.indicador === 'pob_total' && x.periodo === PERIODO);
		return o ? fuenteDe(o) : '';
	});

	function textoRelacion(r: Relacion): string {
		if (r.existe) return r.nombre ?? r.codigo;
		if (r.codigo.endsWith('900')) return `Zona rural (código ${r.codigo}; el INE no publica un polígono de localidad)`;
		return `Código ${r.codigo} (el INE no publica un polígono de localidad)`;
	}

	async function copiar(texto: string, aviso: string) {
		try {
			await navigator.clipboard.writeText(texto);
			mensaje = aviso;
		} catch {
			mensaje = 'No se pudo copiar. Seleccioná el texto y copialo a mano.';
		}
	}

	const hrefMapa = (t: { nivel: string; codigo: string }) => `${resolve('/')}${consultaMapa(t)}`;
</script>

<svelte:head>
	<title>{f.nombre} · {NOMBRE_NIVEL[f.nivel]} · {NOMBRE_SITIO}</title>
	<meta name="description" content="Datos de {f.nombre} ({NOMBRE_NIVEL[f.nivel].toLowerCase()}, código INE {f.codigo}) con su fuente." />
</svelte:head>

<nav aria-label="Ubicación" class="migas">
	<ol>
		<li><a href={resolve('/fichas')}>Uruguay</a></li>
		{#each f.padres as p (p.id)}
			<li><a href={hrefFicha(p)}>{p.nombre}</a></li>
		{/each}
		<li aria-current="page">{f.nombre}</li>
	</ol>
</nav>

<header class="cabecera">
	<div class="identidad">
		<h1>{f.nombre}</h1>
		<p class="chips">
			<span class="chip">{NOMBRE_NIVEL[f.nivel]}</span>
			<span class="chip">Código INE {f.codigo}</span>
			{#if f.codigo_iso}<span class="chip">ISO {f.codigo_iso}</span>{/if}
		</p>
		{#each f.relaciones as r (r.destino_id)}
			<p class="relacion">
				{PERTENECE[r.nivel] ?? 'Pertenece a:'}
				{#if r.existe}<a href={hrefFicha(partesId(r.destino_id))}>{textoRelacion(r)}</a>{:else}{textoRelacion(r)}{/if}
			</p>
		{/each}

		<dl class="kpis">
			{#if valor('pob_total') !== null}
				<div><dt>Personas ({PERIODO})</dt><dd>{numero(valor('pob_total'))}</dd></div>
			{/if}
			{#if valor('viviendas_total') !== null}
				<div><dt>Viviendas ({PERIODO})</dt><dd>{numero(valor('viviendas_total'))}</dd></div>
			{/if}
			{#if f.area_km2 !== null}
				<div><dt>Superficie</dt><dd>{numero(f.area_km2, f.area_km2 < 10 ? 2 : 0)} km²</dd></div>
			{/if}
			{#if f.contenidos.localidad?.length}
				<div><dt>Localidades</dt><dd>{numero(f.contenidos.localidad.length)}</dd></div>
			{/if}
			{#if densidadDepto !== null}
				<div>
					<dt>Densidad ({PERIODO}) <span class="calculada">calculada</span></dt>
					<dd>{numero(densidadDepto, 1)} <span class="unidad-kpi">pers./km²</span></dd>
				</div>
			{/if}
		</dl>
		<!-- AC-V27: de dónde sale cada cifra destacada -->
		<p class="suave notas-kpi">
			{#if fuenteKpi}Personas y viviendas: {fuenteKpi}.{/if}
			{#if f.area_km2 !== null}Superficie{f.contenidos.localidad?.length ? ' y localidades' : ''}: a partir de la geometría del INE (Unidades geoestadísticas Censo 2023).{/if}
			{#if densidadDepto !== null}Densidad: calculada por el observatorio, personas (Censo {PERIODO}) ÷ superficie (geometría del INE); no la publica el INE.{/if}
		</p>

		<div class="acciones">
			<a class="boton primario" href={hrefMapa(f)}>Ver en el mapa</a>
			<button type="button" class="boton" onclick={() => descargarCsv(f)}>Descargar CSV</button>
			<button type="button" class="boton" onclick={() => copiar(url, 'Enlace copiado.')}>Copiar enlace</button>
			<a class="boton" href="#citar">Cómo citar</a>
		</div>
		<p class="visualmente-oculto" role="status" aria-live="polite">{mensaje}</p>
		{#if mensaje}<p class="suave mensaje" aria-hidden="true">{mensaje}</p>{/if}
	</div>
	<div class="ubicacion">
		<MiniMapa nombre={f.nombre} depto={f.depto} nivel={f.nivel} bbox={f.bbox} />
		<!-- AC-V26: las unidades chicas, además, de cerca entre sus vecinos -->
		{#if f.nivel === 'segmento' || f.nivel === 'seccion' || f.nivel === 'localidad'}
			{#key f.id}<LocalizadorCerca nombre={f.nombre} nivel={f.nivel} id={f.id} bbox={f.bbox} />{/key}
		{/if}
	</div>
</header>

<nav aria-label="Secciones de la ficha" class="indice">
	<ul>
		{#each SECCIONES_FICHA as s (s.id)}<li><a href="#{s.id}">{s.titulo}</a></li>{/each}
		{#if contenidos.length}<li><a href="#dentro">Dentro de {f.nombre}</a></li>{/if}
		{#if f.padres.length}<li><a href="#contienen">Niveles que lo contienen</a></li>{/if}
		<li><a href="#fuentes">Fuentes</a></li>
	</ul>
</nav>

{#if f.nivel === 'area_especial'}
	<p class="info">
		Este polígono no tiene datos propios: el INE repite en él los conteos de Artigas, por eso no se guardan.
	</p>
{/if}

{#each SECCIONES_FICHA as s (s.id)}
	{@const lista = observacionesDeSeccion(f, s.temas)}
	{@const { puntuales, series } = separarSeries(lista)}
	<section id={s.id} class="tarjeta seccion" aria-labelledby="titulo-{s.id}">
		<h2 id="titulo-{s.id}">{s.titulo}</h2>
		{#if lista.length === 0}
			{@const arriba = datosEnPadre(f, s.temas)}
			{#if arriba}
				<!-- AC-V24: el tema no se publica a este nivel, pero sí en uno que lo contiene -->
				<p class="info vacio en-padre">
					{arriba.temas.join(' e ')}: se publica por {NOMBRE_NIVEL[arriba.padre.nivel].toLowerCase()} →
					<a href="{hrefFicha(arriba.padre)}#{s.id}">ver {arriba.padre.nombre}</a>
				</p>
			{:else}
				<p class="info vacio">{SIN_FUENTES}</p>
			{/if}
		{/if}
		{#if series.size}
			<SerieFicha ficha={f} {series} pais={data.pais} fuenteDe={fuenteDe} titulo={s.titulo} />
		{/if}
		{#if puntuales.length}
			<TablaDesplazable etiqueta="{s.titulo} en {f.nombre}" clase="tabla-apilada">
				<!-- roles explícitos: con las filas apiladas (CSS) la tabla conserva su semántica -->
				<!-- svelte-ignore a11y_no_redundant_roles (las filas apiladas por CSS pierden la semántica de tabla) -->
				<table role="table">
					<caption class="visualmente-oculto">{s.titulo} en {f.nombre}</caption>
					<!-- svelte-ignore a11y_no_redundant_roles (las filas apiladas por CSS pierden la semántica de tabla) -->
					<thead role="rowgroup">
						<!-- svelte-ignore a11y_no_redundant_roles (las filas apiladas por CSS pierden la semántica de tabla) -->
						<tr role="row">
							<th role="columnheader" scope="col">Indicador</th>
							<th role="columnheader" scope="col" class="num">Valor</th>
							<th role="columnheader" scope="col">Período</th>
							<th role="columnheader" scope="col">Fuente</th>
							{#if f.padres.length}<th role="columnheader" scope="col">En relación con</th>{/if}
						</tr>
					</thead>
					<!-- svelte-ignore a11y_no_redundant_roles (las filas apiladas por CSS pierden la semántica de tabla) -->
					<tbody role="rowgroup">
						{#each puntuales as o (o.indicador + o.periodo)}
							<!-- svelte-ignore a11y_no_redundant_roles (las filas apiladas por CSS pierden la semántica de tabla) -->
							<tr role="row">
								<td role="cell" data-etiqueta="Indicador">{ind(o)?.nombre ?? o.indicador}</td>
								<td role="cell" class="num" data-etiqueta="Valor">
									{publicado(o.valor)}
									{ind(o)?.unidad}
									{#if o.es_estimado}<span class="estimado">estimado</span>{/if}
								</td>
								<td role="cell" data-etiqueta="Período">{o.periodo}</td>
								<td role="cell" data-etiqueta="Fuente">{fuenteDe(o)}</td>
								{#if f.padres.length}
									<td role="cell" data-etiqueta="En relación con">{partes(o, f).map((p) => p.texto).join(' · ')}</td>
								{/if}
							</tr>
						{/each}
					</tbody>
				</table>
			</TablaDesplazable>
		{/if}
		{#if s.id === 'poblacion'}
			{#if nota}<p class="info nota">{nota}</p>{/if}
			<p class="suave">Pirámide de población: todavía no hay datos por edad cargados.</p>
		{/if}
	</section>
{/each}

{#if contenidos.length && activa}
	<section id="dentro" aria-labelledby="titulo-dentro">
		<h2 id="titulo-dentro">Dentro de {f.nombre}</h2>
		<div role="tablist" aria-label="Unidades dentro de {f.nombre}" class="pestanas">
			{#each contenidos as [nivel, lista] (nivel)}
				<button
					type="button"
					role="tab"
					id="pestana-{nivel}"
					aria-selected={activa === nivel}
					aria-controls="panel-dentro"
					tabindex={activa === nivel ? 0 : -1}
					onclick={() => (pestana = nivel)}
					onkeydown={(e) => {
						const i = contenidos.findIndex(([n]) => n === nivel);
						const paso = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
						if (!paso) return;
						const sig = contenidos[(i + paso + contenidos.length) % contenidos.length][0];
						pestana = sig;
						document.getElementById(`pestana-${sig}`)?.focus();
					}}
				>
					{NOMBRE_NIVEL[nivel]} ({numero(lista.length)})
				</button>
			{/each}
		</div>
		<div id="panel-dentro" role="tabpanel" aria-labelledby="pestana-{activa}" class="tarjeta">
			<TablaDesplazable etiqueta="{NOMBRE_NIVEL[activa]} dentro de {f.nombre}">
				<table>
					<caption class="visualmente-oculto">{NOMBRE_NIVEL[activa]} dentro de {f.nombre}</caption>
					<thead>
						<tr>
							<th scope="col">Nombre</th>
							<th scope="col">Código</th>
							<th scope="col" class="num">Personas ({PERIODO})</th>
							<th scope="col" class="num">Viviendas ({PERIODO})</th>
							<th scope="col"><span class="visualmente-oculto">Mapa</span></th>
						</tr>
					</thead>
					<tbody>
						{#each f.contenidos[activa] ?? [] as h (h.id)}
							<tr>
								<td><a href={hrefFicha(h)}>{h.nombre}</a></td>
								<td>{h.codigo}</td>
								<td class="num">{numero(valorDe(h, 'pob_total', PERIODO))}</td>
								<td class="num">{numero(valorDe(h, 'viviendas_total', PERIODO))}</td>
								<td><a href={hrefMapa(h)} aria-label="Ver en el mapa: {h.nombre}">Ver en el mapa</a></td>
							</tr>
						{/each}
					</tbody>
				</table>
			</TablaDesplazable>
			<p class="suave fuente">Fuente: INE, Unidades geoestadísticas Censo 2023. Valores publicados para cada unidad.</p>
		</div>
	</section>
{/if}

{#if f.padres.length}
	<section id="contienen" aria-labelledby="titulo-contienen">
		<h2 id="titulo-contienen">Más datos en los niveles que contienen este territorio</h2>
		<div class="tarjetas">
			{#each [...f.padres].reverse() as p (p.id)}
				<article class="tarjeta">
					<h3><a href={hrefFicha(p)}>{p.nombre}</a></h3>
					<p class="suave">{NOMBRE_NIVEL[p.nivel]} · Código INE {p.codigo}</p>
					<dl class="valores">
						<!-- solo los valores del Censo 2023; las series (p. ej. la ECH) están en la ficha del padre -->
						{#each Object.entries(p.valores).filter(([, v]) => v[PERIODO] != null) as [codigo, porPeriodo] (codigo)}
							<div>
								<dt>{f.indicadores[codigo]?.nombre ?? codigo} ({PERIODO})</dt>
								<dd>{numero(porPeriodo[PERIODO])} {f.indicadores[codigo]?.unidad}</dd>
							</div>
						{/each}
					</dl>
				</article>
			{/each}
		</div>
		<p class="suave fuente">Fuente: INE, Unidades geoestadísticas Censo 2023.</p>
	</section>
{/if}

{#if f.nivel === 'segmento'}
	<section class="tarjeta seccion" aria-labelledby="titulo-hechos">
		<h2 id="titulo-hechos">Hechos registrados</h2>
		<p class="info vacio">Todavía no hay fuentes de hechos con ubicación (por ejemplo, siniestros o centros educativos).</p>
	</section>
	<section class="tarjeta seccion" aria-labelledby="titulo-anteriores">
		<h2 id="titulo-anteriores">En censos anteriores</h2>
		<p class="info vacio">Todavía no está cargada la correspondencia con los segmentos del Censo 2011.</p>
	</section>
{/if}

<section id="fuentes" class="tarjeta seccion" aria-labelledby="titulo-fuentes">
	<h2 id="titulo-fuentes">Fuentes de esta ficha</h2>
	{#if Object.keys(f.capturas).length === 0}
		<p class="suave">Esta ficha no tiene datos propios.</p>
	{/if}
	<!-- Una entrada por fuente; los archivos (capturas) plegados (AC-V18). -->
	<ul class="fuentes">
		{#each fuentesDeFicha(f) as g (g.id)}
			{@const fu = g.fuente}
			<li>
				<strong><a href={resolve('/fuentes/[id]', { id: g.id })}>{fu?.nombre ?? g.id}</a></strong>
				({fu?.organismo}). Última captura procesada el {fecha(g.ultima.fecha_proceso)}.
				{#if fu?.url_descarga}<a href={fu.url_descarga}>Original</a> ·{/if}
				{#if fu?.pagina}<a href={fu.pagina}>Metodología y metadatos</a>.{/if}
				Licencia: «{fu?.licencia}»
				<details class="archivos">
					<summary>{g.capturas.length === 1 ? 'Ver el archivo' : `Ver los ${g.capturas.length} archivos`}</summary>
					<ul>
						{#each g.capturas as c (c.id)}
							<li>
								<code>{c.archivo}</code>, sha256 <code>{c.sha256.slice(0, 16)}…</code>, procesado el {fecha(c.fecha_proceso)}.
							</li>
						{/each}
					</ul>
				</details>
			</li>
		{/each}
	</ul>

	<h3 id="citar">Cómo citar</h3>
	<blockquote class="cita">{textoCita || `Observatorio Uruguay. «${f.nombre}» (${NOMBRE_NIVEL[f.nivel].toLowerCase()}, código INE ${f.codigo}).`}</blockquote>
	<button type="button" class="boton" onclick={() => copiar(textoCita, 'Cita copiada.')} disabled={!textoCita}>
		Copiar cita
	</button>
</section>

<style>
	section {
		margin-top: var(--espacio-5);
	}

	.migas ol {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-1);
		align-items: center;
		list-style: none;
		padding: 0;
		margin: 0 0 var(--espacio-2);
		font-size: var(--texto-s);
	}

	.migas li + li::before {
		content: '›';
		margin-right: var(--espacio-1);
		color: var(--texto-suave);
	}

	.migas a,
	.indice a,
	td a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
	}

	.cabecera {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 220px;
		gap: var(--espacio-5);
		align-items: start;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-2);
	}

	.chip {
		background: var(--azul-1);
		border: 1px solid var(--borde);
		border-radius: 999px;
		padding: var(--espacio-1) var(--espacio-3);
		font-size: var(--texto-s);
	}

	.kpis {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: var(--espacio-3);
		margin: var(--espacio-4) 0;
	}

	.kpis div {
		background: var(--tarjeta);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		padding: var(--espacio-3) var(--espacio-4);
	}

	.kpis dt {
		font-size: var(--texto-s);
		color: var(--texto-suave);
	}

	.notas-kpi {
		margin: calc(-1 * var(--espacio-2)) 0 var(--espacio-4);
		font-size: var(--texto-xs);
	}

	.calculada {
		margin-left: var(--espacio-1);
		padding: 0 var(--espacio-1);
		border: 1px solid var(--info-borde);
		border-radius: var(--radio-s);
		background: var(--info-fondo);
		color: var(--info-texto);
		font-size: var(--texto-xs);
	}

	.unidad-kpi {
		font-size: var(--texto-s);
		font-weight: 400;
	}

	.kpis dd {
		margin: 0;
		font-family: var(--fuente-titulos);
		font-size: var(--texto-xl);
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}

	.acciones {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-2);
	}

	.boton {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: var(--toque-min);
		padding: 0 var(--espacio-4);
		border-radius: var(--radio-m);
		border: 1px solid var(--borde);
		background: var(--tarjeta);
		color: var(--primario);
		font: inherit;
		font-weight: 600;
		text-decoration: none;
		cursor: pointer;
	}

	.boton.primario {
		background: var(--primario);
		border-color: var(--primario);
		color: var(--sobre-primario);
	}

	.boton:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.mensaje {
		margin: var(--espacio-2) 0 0;
	}

	.indice {
		position: sticky;
		top: 0;
		z-index: 5;
		background: var(--fondo);
		border-bottom: 1px solid var(--borde);
		margin-top: var(--espacio-5);
	}

	/* desplazable sin barra visible; el borde derecho se desvanece para mostrar que hay más (AC-V25) */
	.indice ul {
		display: flex;
		gap: var(--espacio-1) var(--espacio-4);
		list-style: none;
		margin: 0;
		padding: 0 40px 0 0; /* tanto como el desvanecido: el último enlace termina fuera de él */
		overflow-x: auto;
		white-space: nowrap;
		scrollbar-width: none;
		mask-image: linear-gradient(to right, #000 calc(100% - 40px), transparent);
	}

	.indice ul::-webkit-scrollbar {
		display: none;
	}

	.indice ul:has(:focus-visible) {
		mask-image: none;
	}

	.seccion h2 {
		margin-bottom: var(--espacio-3);
	}

	.vacio,
	.nota {
		margin: var(--espacio-3) 0 0;
	}

	.estimado {
		margin-left: var(--espacio-1);
		padding: 0 var(--espacio-1);
		border: 1px solid var(--aviso-borde);
		border-radius: var(--radio-s);
		color: var(--aviso-texto);
		background: var(--aviso-fondo);
		font-size: var(--texto-xs);
	}

	.pestanas {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-1);
		margin-bottom: var(--espacio-2);
	}

	.pestanas button {
		min-height: var(--toque-min);
		padding: 0 var(--espacio-4);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m) var(--radio-m) 0 0;
		background: var(--tarjeta);
		font: inherit;
		color: var(--texto);
		cursor: pointer;
	}

	.pestanas button[aria-selected='true'] {
		background: var(--primario);
		border-color: var(--primario);
		color: var(--sobre-primario);
		font-weight: 600;
	}

	.tarjetas {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
		gap: var(--espacio-4);
	}

	.tarjetas h3 {
		margin: 0;
	}

	.tarjetas h3 a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
	}

	.valores {
		margin: var(--espacio-2) 0 0;
		display: grid;
		gap: var(--espacio-1);
	}

	.valores div {
		display: flex;
		justify-content: space-between;
		gap: var(--espacio-2);
		border-bottom: 1px solid var(--borde);
		padding: var(--espacio-1) 0;
		font-size: var(--texto-s);
	}

	.valores dd {
		margin: 0;
		font-variant-numeric: tabular-nums;
		text-align: right;
	}

	.fuente {
		font-size: var(--texto-xs);
	}

	.fuentes > li {
		margin-bottom: var(--espacio-3);
	}

	.archivos summary {
		cursor: pointer;
		min-height: var(--toque-min);
		display: inline-flex;
		align-items: center;
		color: var(--primario);
	}

	.archivos ul {
		margin: 0;
		padding-left: var(--espacio-4);
		font-size: var(--texto-s);
	}

	code {
		font-size: var(--texto-xs);
		overflow-wrap: anywhere;
	}

	.cita {
		margin: 0 0 var(--espacio-3);
		padding: var(--espacio-3) var(--espacio-4);
		border-left: 4px solid var(--primario);
		background: var(--fondo);
		overflow-wrap: anywhere;
	}

	/* AC-V25: los valores KPI no se cortan en dos líneas */
	@media (max-width: 600px) {
		.kpis dd {
			white-space: nowrap;
			font-size: var(--texto-l);
		}
	}

	@media (max-width: 700px) {
		.cabecera {
			grid-template-columns: minmax(0, 1fr);
		}

		.ubicacion {
			max-width: 160px;
		}
	}
</style>
