<script lang="ts">
	// F2.8c (AC-L25): series de una fuente con varios períodos (p. ej. la ECH) en la ficha: gráfico de líneas del
	// territorio frente al total del país (tal como lo publica la fuente, desde su primer informe), los últimos
	// valores y la tabla con toda la serie (equivalente accesible del gráfico; es lo que baja el CSV, AC-F5).
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import type { Ficha, Observacion } from '#lib/datos.ts';
	import { publicado } from '#lib/formato.ts';
	import { etiquetaPeriodo } from '#lib/mapa/estado.ts';
	import AdvertenciasFuente from '#lib/AdvertenciasFuente.svelte';
	import { puntosSerie } from './logica.ts';

	let {
		ficha,
		series,
		pais,
		fuenteDe,
		titulo
	}: {
		ficha: Ficha;
		series: Map<string, Observacion[]>;
		pais: Ficha | null;
		fuenteDe: (o: Observacion) => string;
		titulo: string;
	} = $props();

	// Orden del catálogo de la fuente: tasas primero, después miles de personas; lo demás, alfabético.
	const ORDEN = ['tasa_actividad', 'tasa_empleo', 'tasa_desempleo', 'tasa_no_registro', 'activos', 'ocupados', 'desocupados'];
	const rango_ = (c: string) => (ORDEN.includes(c) ? ORDEN.indexOf(c) : ORDEN.length);
	const codigos = $derived([...series.keys()].sort((a, b) => rango_(a) - rango_(b) || a.localeCompare(b)));
	let elegido = $state<string | null>(null);
	let indicador = $derived(elegido && series.has(elegido) ? elegido : (codigos[0] ?? ''));
	let info = $derived(ficha.indicadores[indicador]);
	let p = $derived(puntosSerie(series.get(indicador) ?? [], ficha.nivel === 'pais' ? null : pais, indicador));
	const idSelector = $derived(`serie-${ficha.nivel}-${ficha.codigo}`);

	// Geometría del gráfico (viewBox; el SVG escala al ancho disponible).
	const W = 640;
	const H = 240;
	const M = { izq: 44, der: 12, arr: 12, aba: 28 };
	let x = $derived.by(() => {
		const n = Math.max(1, p.periodos.length - 1);
		const pos = new Map(p.periodos.map((per, i) => [per, M.izq + (i * (W - M.izq - M.der)) / n]));
		return (per: string) => pos.get(per) ?? null;
	});
	let rango = $derived.by(() => {
		const v = [...p.territorio, ...p.pais].map((q) => q.valor);
		if (!v.length) return { min: 0, max: 1 };
		const min = Math.min(...v);
		const max = Math.max(...v);
		const margen = (max - min || Math.abs(max) || 1) * 0.1;
		return { min: min - margen, max: max + margen };
	});
	const y = (v: number) => M.arr + ((rango.max - v) * (H - M.arr - M.aba)) / (rango.max - rango.min);
	const linea = (pts: { periodo: string; valor: number }[]) =>
		pts
			.map((q) => [x(q.periodo), y(q.valor)] as const)
			.filter(([px]) => px !== null)
			.map(([px, py]) => `${px!.toFixed(1)},${py.toFixed(1)}`)
			.join(' ');
	let marcas = $derived([rango.min, (rango.min + rango.max) / 2, rango.max]);
	let ultimo = $derived(p.territorio.at(-1));
	let ultimoObs = $derived((series.get(indicador) ?? []).at(-1));
	let fuenteRef = $derived(ultimoObs ? ficha.fuentes[ficha.capturas[ultimoObs.captura_id]?.fuente_id] : undefined);
	let paisUltimo = $derived(p.pais.find((q) => q.periodo === ultimo?.periodo));
	let resumen = $derived(
		ultimo
			? `${info?.nombre}: ${p.territorio.length} períodos desde ${etiquetaPeriodo(p.territorio[0].periodo)}; ` +
					`último, ${etiquetaPeriodo(ultimo.periodo)}: ${publicado(ultimo.valor)} ${info?.unidad ?? ''}` +
					(paisUltimo ? `; total del país: ${publicado(paisUltimo.valor)} ${info?.unidad ?? ''}` : '')
			: ''
	);
</script>

<div class="serie">
	<div class="campo">
		<label for={idSelector}>Indicador</label>
		<select id={idSelector} value={indicador} onchange={(e) => (elegido = e.currentTarget.value)}>
			{#each codigos as c (c)}<option value={c}>{ficha.indicadores[c]?.nombre ?? c}</option>{/each}
		</select>
	</div>

	<figure>
		<svg viewBox="0 0 {W} {H}" role="img" aria-label={resumen} data-puntos={p.territorio.length} data-puntos-pais={p.pais.length}>
			{#each marcas as m (m)}
				<line class="guia" x1={M.izq} x2={W - M.der} y1={y(m)} y2={y(m)} />
				<text class="eje" x={M.izq - 6} y={y(m) + 4} text-anchor="end">{publicado(Math.round(m * 10) / 10)}</text>
			{/each}
			{#if p.periodos.length}
				<text class="eje" x={M.izq} y={H - 8}>{etiquetaPeriodo(p.periodos[0]).replace('Trimestre móvil ', '')}</text>
				<text class="eje" x={W - M.der} y={H - 8} text-anchor="end"
					>{etiquetaPeriodo(p.periodos.at(-1)!).replace('Trimestre móvil ', '')}</text
				>
			{/if}
			{#if p.pais.length}<polyline class="pais" points={linea(p.pais)} />{/if}
			<polyline class="territorio" points={linea(p.territorio)} />
		</svg>
		<figcaption>
			<span class="item"><span class="clave territorio"></span>{ficha.nombre}</span>
			{#if p.pais.length}
				<span class="item"
					><span class="clave pais"></span>Total del país (lo publica el INE desde {etiquetaPeriodo(p.pais[0].periodo)})</span
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
					{publicado(ultimo.valor)}
					{info?.unidad}
					{#if paisUltimo}<span class="suave"> (país: {publicado(paisUltimo.valor)} {info?.unidad})</span>{/if}
				</dd>
			</div>
		</dl>
	{/if}

	<AdvertenciasFuente fuente={fuenteRef?.nombre ?? ''} advertencias={fuenteRef?.advertencias ?? []} />

	<details>
		<summary>Ver los datos de la serie ({[...series.values()].reduce((n, s) => n + s.length, 0)} valores)</summary>
		<TablaDesplazable etiqueta="{titulo}: serie en {ficha.nombre}">
			<table>
				<caption class="visualmente-oculto">{titulo}: serie en {ficha.nombre}</caption>
				<thead>
					<tr>
						<th scope="col">Indicador</th>
						<th scope="col" class="num">Valor</th>
						<th scope="col">Período</th>
						<th scope="col">Fuente</th>
					</tr>
				</thead>
				<tbody>
					{#each [...series.values()].flat() as o (o.indicador + o.periodo)}
						<tr>
							<td>{ficha.indicadores[o.indicador]?.nombre ?? o.indicador}</td>
							<td class="num">
								{publicado(o.valor)}
								{ficha.indicadores[o.indicador]?.unidad}
								{#if o.es_estimado}<span class="estimado">estimado</span>{/if}
							</td>
							<td>{o.periodo}</td>
							<td>{fuenteDe(o)}</td>
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

	.campo {
		display: flex;
		gap: var(--espacio-2);
		align-items: center;
		flex-wrap: wrap;
	}

	select {
		min-height: var(--toque-min);
	}
</style>
