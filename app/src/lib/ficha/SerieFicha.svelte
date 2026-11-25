<script lang="ts">
	// F2.8c (AC-L25): series de una fuente con varios períodos (p. ej. la ECH) en la ficha: gráfico de líneas del
	// territorio frente al total del país (tal como lo publica la fuente, desde su primer informe), los últimos
	// valores y la tabla con toda la serie (equivalente accesible del gráfico; es lo que baja el CSV, AC-F5).
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import type { Ficha, Observacion } from '#lib/datos.ts';
	import { numero, publicado } from '#lib/formato.ts';
	import { etiquetaPeriodo } from '#lib/mapa/estado.ts';
	import AdvertenciasFuente from '#lib/AdvertenciasFuente.svelte';
	import { decimalesComunes, indicesEtiquetas, marcasRedondas, puntosSerie } from './logica.ts';

	let {
		ficha,
		series,
		pais,
		fuenteDe,
		titulo,
		ordenar
	}: {
		ficha: Ficha;
		series: Map<string, Observacion[]>;
		pais: Ficha | null;
		fuenteDe: (o: Observacion) => string;
		titulo: string;
		/** Orden propio de los indicadores del selector (p. ej. la serie de educación: el total primero). */
		ordenar?: (codigos: string[]) => string[];
	} = $props();

	// Orden del catálogo de la fuente: tasas primero, después miles de personas; lo demás, alfabético.
	const ORDEN = ['tasa_actividad', 'tasa_empleo', 'tasa_desempleo', 'tasa_no_registro', 'activos', 'ocupados', 'desocupados'];
	const rango_ = (c: string) => (ORDEN.includes(c) ? ORDEN.indexOf(c) : ORDEN.length);
	const codigos = $derived(
		ordenar ? ordenar([...series.keys()]) : [...series.keys()].sort((a, b) => rango_(a) - rango_(b) || a.localeCompare(b))
	);
	let elegido = $state<string | null>(null);
	let indicador = $derived(elegido && series.has(elegido) ? elegido : (codigos[0] ?? ''));
	let info = $derived(ficha.indicadores[indicador]);
	let p = $derived(puntosSerie(series.get(indicador) ?? [], ficha.nivel === 'pais' ? null : pais, indicador));
	const idSelector = $derived(`serie-${ficha.nivel}-${ficha.codigo}`);

	// Geometría del gráfico (viewBox; el SVG escala al ancho disponible).
	const W = 640;
	const H = 240;
	let x = $derived.by(() => {
		const n = Math.max(1, p.periodos.length - 1);
		const pos = new Map(p.periodos.map((per, i) => [per, M.izq + (i * (W - M.izq - M.der)) / n]));
		return (per: string) => pos.get(per) ?? null;
	});
	// AC-V20: el eje y va de una marca redonda a otra (paso de 1, 2, 2,5 o 5 × 10ⁿ).
	let marcas = $derived.by(() => {
		const v = [...p.territorio, ...p.pais].map((q) => q.valor);
		return v.length ? marcasRedondas(Math.min(...v), Math.max(...v)) : [0, 1];
	});
	let rango = $derived({ min: marcas[0], max: marcas.at(-1)! });
	let decimalesEje = $derived(decimalesComunes(marcas));
	// El margen izquierdo crece con el largo de las marcas del eje y (p. ej. «120.000» en los ingresos).
	let M = $derived({ izq: Math.max(44, 12 + 7.5 * Math.max(...marcas.map((m) => numero(m, decimalesEje).length))), der: 12, arr: 12, aba: 28 });
	/** "2021-12/2022-02" -> "dic 21–feb 22" (etiqueta corta del eje x). */
	const corta = (per: string) =>
		/^\d{4}$/.test(per)
			? per // un año (p. ej. los totales anuales de ingresos) va completo
			: etiquetaPeriodo(per)
			.replace('Trimestre móvil ', '')
			.replace(/(\d{2})(\d{2})/g, '$2');
	let etiquetasX = $derived(indicesEtiquetas(p.periodos.length, 5).map((i) => p.periodos[i]));
	const y = (v: number) => M.arr + ((rango.max - v) * (H - M.arr - M.aba)) / (rango.max - rango.min);
	const linea = (pts: { periodo: string; valor: number }[]) =>
		pts
			.map((q) => [x(q.periodo), y(q.valor)] as const)
			.filter(([px]) => px !== null)
			.map(([px, py]) => `${px!.toFixed(1)},${py.toFixed(1)}`)
			.join(' ');
	let ultimo = $derived(p.territorio.at(-1));
	let ultimoObs = $derived((series.get(indicador) ?? []).at(-1));
	let fuenteRef = $derived(ultimoObs ? ficha.fuentes[ficha.capturas[ultimoObs.captura_id]?.fuente_id] : undefined);
	let paisUltimo = $derived(p.pais.find((q) => q.periodo === ultimo?.periodo));
	// AC-V20: territorio y país con los mismos decimales
	let decimales = $derived(decimalesComunes([ultimo?.valor, paisUltimo?.valor].filter((v): v is number => v != null)));
	let siglasFuente = $derived(fuenteRef?.organismo.replace(/^.*\((\w+)\)$/, '$1') ?? '');
	let resumen = $derived(
		ultimo
			? `${info?.nombre}: ${p.territorio.length} períodos desde ${etiquetaPeriodo(p.territorio[0].periodo)}; ` +
					`último, ${etiquetaPeriodo(ultimo.periodo)}: ${publicado(ultimo.valor)} ${info?.unidad ?? ''}` +
					(paisUltimo ? `; total del país: ${publicado(paisUltimo.valor)} ${info?.unidad ?? ''}` : '')
			: ''
	);
</script>

<div class="serie">
	{#if codigos.length > 1}
		<div class="campo">
			<label for={idSelector}>Indicador</label>
			<select id={idSelector} value={indicador} onchange={(e) => (elegido = e.currentTarget.value)}>
				{#each codigos as c (c)}<option value={c}>{ficha.indicadores[c]?.nombre ?? c}</option>{/each}
			</select>
		</div>
	{:else if info}
		<p class="nombre-serie">{info.nombre}</p>
	{/if}

	<figure>
		<svg viewBox="0 0 {W} {H}" role="img" aria-label={resumen} data-puntos={p.territorio.length} data-puntos-pais={p.pais.length}>
			{#each marcas as m (m)}
				<line class="guia" x1={M.izq} x2={W - M.der} y1={y(m)} y2={y(m)} />
				<text class="eje" x={M.izq - 6} y={y(m) + 4} text-anchor="end">{numero(m, decimalesEje)}</text>
			{/each}
			{#each etiquetasX as per, i (per)}
				<text
					class="eje"
					x={x(per)}
					y={H - 8}
					text-anchor={i === 0 ? 'start' : i === etiquetasX.length - 1 ? 'end' : 'middle'}>{corta(per)}</text
				>
			{/each}
			{#if p.pais.length}<polyline class="pais" points={linea(p.pais)} />{/if}
			<polyline class="territorio" points={linea(p.territorio)} />
		</svg>
		<figcaption>
			<span class="item"><span class="clave territorio"></span>{ficha.nombre}</span>
			{#if p.pais.length}
				<span class="item"
					><span class="clave pais"></span>Total del país ({siglasFuente}, desde {etiquetaPeriodo(p.pais[0].periodo).replace(
						'Trimestre móvil ',
						''
					)})</span
				>
			{/if}
			<span class="item">{info?.unidad} · Fuente: {ultimoObs ? fuenteDe(ultimoObs) : ''}</span>
		</figcaption>
	</figure>

	{#if ultimo}
		<dl class="ultimo">
			<div>
				<dt>{info?.nombre} · {etiquetaPeriodo(ultimo.periodo)}</dt>
				<dd>
					{numero(ultimo.valor, decimales)}
					{info?.unidad}
					{#if paisUltimo}<span class="suave"> (país: {numero(paisUltimo.valor, decimales)} {info?.unidad})</span>{/if}
				</dd>
			</div>
		</dl>
	{/if}

	<AdvertenciasFuente
		fuente={fuenteRef?.nombre ?? ''}
		advertencias={fuenteRef?.advertencias ?? []}
		resumen={fuenteRef?.resumen_advertencias}
	/>

	<details>
		<summary>Ver los datos de la serie ({[...series.values()].reduce((n, s) => n + s.length, 0)} valores)</summary>
		<TablaDesplazable etiqueta="{titulo}: serie en {ficha.nombre}" clase="tabla-apilada">
			<!-- svelte-ignore a11y_no_redundant_roles (las filas apiladas por CSS pierden la semántica de tabla) -->
			<table role="table">
				<caption class="visualmente-oculto">{titulo}: serie en {ficha.nombre}</caption>
				<!-- svelte-ignore a11y_no_redundant_roles (las filas apiladas por CSS pierden la semántica de tabla) -->
				<thead role="rowgroup">
					<!-- svelte-ignore a11y_no_redundant_roles (las filas apiladas por CSS pierden la semántica de tabla) -->
					<tr role="row">
						<th role="columnheader" scope="col">Indicador</th>
						<th role="columnheader" scope="col" class="num">Valor</th>
						<th role="columnheader" scope="col">Período</th>
						<th role="columnheader" scope="col">Fuente</th>
					</tr>
				</thead>
				<!-- svelte-ignore a11y_no_redundant_roles (las filas apiladas por CSS pierden la semántica de tabla) -->
				<tbody role="rowgroup">
					{#each [...series.values()].flat() as o (o.indicador + o.periodo)}
						<!-- svelte-ignore a11y_no_redundant_roles (las filas apiladas por CSS pierden la semántica de tabla) -->
						<tr role="row">
							<td role="cell" data-etiqueta="Indicador">{ficha.indicadores[o.indicador]?.nombre ?? o.indicador}</td>
							<td role="cell" class="num" data-etiqueta="Valor">
								{publicado(o.valor)}
								{ficha.indicadores[o.indicador]?.unidad}
								{#if o.es_estimado}<span class="estimado">estimado</span>{/if}
							</td>
							<td role="cell" data-etiqueta="Período">{o.periodo}</td>
							<td role="cell" data-etiqueta="Fuente">{fuenteDe(o)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</TablaDesplazable>
	</details>
</div>

<style>
	.serie {
		display: grid;
		gap: var(--espacio-3);
	}

	figure {
		margin: 0;
	}

	svg {
		width: 100%;
		height: auto;
		display: block;
	}

	.guia {
		stroke: var(--borde);
		stroke-width: 1;
	}

	.eje {
		fill: var(--texto-suave);
		font-size: 12px;
	}

	polyline {
		fill: none;
		stroke-width: 2.5;
		stroke-linejoin: round;
	}

	polyline.territorio {
		stroke: var(--primario);
	}

	polyline.pais {
		stroke: var(--texto-suave);
		stroke-dasharray: 6 4;
	}

	figcaption {
		font-size: var(--texto-s);
		color: var(--texto-suave);
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--espacio-1) var(--espacio-2);
	}

	.item {
		display: inline-flex;
		align-items: center;
		gap: var(--espacio-1);
	}

	.clave {
		display: inline-block;
		width: 1.5em;
		height: 0;
		border-top: 3px solid var(--primario);
	}

	.clave.pais {
		border-top: 3px dashed var(--texto-suave);
	}

	.ultimo {
		margin: 0;
	}

	.ultimo dt {
		font-size: var(--texto-s);
		color: var(--texto-suave);
	}

	.ultimo dd {
		margin: 0;
		font-size: var(--texto-l);
		font-weight: 600;
	}

	.estimado {
		font-size: var(--texto-xs);
		color: var(--texto-suave);
		margin-left: var(--espacio-1);
	}

	summary {
		cursor: pointer;
		min-height: var(--toque-min);
		display: flex;
		align-items: center;
	}

	.nombre-serie {
		margin: 0;
		font-weight: 600;
	}

	.campo {
		display: flex;
		gap: var(--espacio-2);
		align-items: center;
		flex-wrap: wrap;
	}

	/* con el estilo de los demás selectores del sitio (AC-V20) */
	select {
		min-height: var(--toque-min);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		background: var(--tarjeta);
		padding: 0 var(--espacio-3);
		font: inherit;
		color: var(--texto);
	}
</style>
