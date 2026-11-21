<script lang="ts">
	// F3.7b (AC-I21, AC-I24): series de ingresos de la ECH (país, Montevideo y regiones). En vez de una lista de diez
	// indicadores, el usuario elige medida, aguinaldo, valor locativo, base de precios y trimestres o años; el
	// gráfico es el de las demás series (SerieFicha). Por defecto, la variante titular del INE.
	import type { Ficha, Observacion } from '#lib/datos.ts';
	import { etiquetaPeriodo } from '#lib/mapa/estado.ts';
	import SerieFicha from './SerieFicha.svelte';
	import { INGRESO_POR_DEFECTO, indicadorIngreso, serieIngreso, type OpcionesIngreso } from './logica.ts';

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

	let o = $state<OpcionesIngreso>({ ...INGRESO_POR_DEFECTO });
	let codigo = $derived(indicadorIngreso(o));
	let elegida = $derived(new Map([[codigo, serieIngreso(series, o)]]));
	let ultimo = $derived(elegida.get(codigo)?.filter((x) => x.valor !== null).at(-1));
	let unidad = $derived(ficha.indicadores[codigo]?.unidad ?? '');
	const id = $derived(`ingresos-${ficha.nivel}-${ficha.codigo}`);
</script>

<div class="ingresos">
	<fieldset class="opciones">
		<legend>Elegir la serie</legend>
		<div class="grupo" role="radiogroup" aria-labelledby="{id}-medida">
			<span id="{id}-medida" class="rotulo">Medida</span>
			<label><input type="radio" name="{id}-medida" value="hogar" bind:group={o.medida} /> De los hogares</label>
			<label><input type="radio" name="{id}-medida" value="pc" bind:group={o.medida} /> Per cápita</label>
		</div>
		<div class="grupo" role="radiogroup" aria-labelledby="{id}-precios">
			<span id="{id}-precios" class="rotulo">Precios</span>
			<label><input type="radio" name="{id}-precios" value="corrientes" bind:group={o.base} /> Corrientes</label>
			<label><input type="radio" name="{id}-precios" value="ene2005" bind:group={o.base} /> De enero de 2005</label>
		</div>
		<!-- a precios de enero de 2005 las casillas se ven sin marcar (es la única serie publicada); la preferencia
		     se conserva para cuando se vuelve a precios corrientes -->
		<div class="grupo" role="group" aria-labelledby="{id}-incluye">
			<span id="{id}-incluye" class="rotulo">Incluye</span>
			<label
				><input
					type="checkbox"
					checked={o.base === 'ene2005' ? false : o.aguinaldo}
					onchange={(e) => (o.aguinaldo = e.currentTarget.checked)}
					disabled={o.base === 'ene2005'}
					aria-describedby={o.base === 'ene2005' ? `${id}-nota` : undefined}
				/> Aguinaldo</label
			>
			<label
				><input
					type="checkbox"
					checked={o.base === 'ene2005' ? false : o.valorLocativo}
					onchange={(e) => (o.valorLocativo = e.currentTarget.checked)}
					disabled={o.base === 'ene2005'}
					aria-describedby={o.base === 'ene2005' ? `${id}-nota` : undefined}
				/> Valor locativo</label
			>
		</div>
		<div class="grupo" role="radiogroup" aria-labelledby="{id}-frecuencia">
			<span id="{id}-frecuencia" class="rotulo">Ver</span>
			<label><input type="radio" name="{id}-frecuencia" value="trimestre" bind:group={o.frecuencia} /> Trimestres</label>
			<label><input type="radio" name="{id}-frecuencia" value="anio" bind:group={o.frecuencia} /> Totales anuales</label>
		</div>
		{#if o.base === 'ene2005'}
			<p id="{id}-nota" class="suave nota-opciones">A precios de enero de 2005 el INE publica solo la serie sin aguinaldo y sin valor locativo.</p>
		{/if}
	</fieldset>

	{#if elegida.get(codigo)?.length}
		<SerieFicha {ficha} series={elegida} {pais} {fuenteDe} {titulo} />
	{:else}
		<p class="info">Esta serie no está en los datos de {ficha.nombre}.</p>
	{/if}

	<!-- AC-I24: base de precios y período, fuente, revisión y cambio de concepto -->
	<div class="info notas-ingresos">
		<p>
			{#if ultimo}<strong>{unidad} · {etiquetaPeriodo(ultimo.periodo)}</strong>.{' '}{/if}Fuente: INE, Encuesta Continua de
			Hogares. Las cifras están sujetas a revisión.
			{#if o.frecuencia === 'anio'}El total de cada año es el promedio de sus cuatro trimestres.{/if}
		</p>
		<p>
			Desde 2025 el INE mide el ingreso disponible ajustado (YDA), que no incluye las cuotas de salud del FONASA ni
			de Sanidad militar o policial; toda la serie desde 2016 está calculada así, por lo que no se compara con
			cifras de informes anteriores a 2025.
		</p>
	</div>
</div>

<style>
	.ingresos {
		display: grid;
		gap: var(--espacio-3);
	}

	.opciones {
		display: flex;
		flex-wrap: wrap;
		gap: var(--espacio-2) var(--espacio-4);
		border: 1px solid var(--borde);
		border-radius: 10px;
		padding: var(--espacio-3);
		margin: 0;
	}

	legend {
		font-weight: 600;
		padding: 0 var(--espacio-1);
	}

	.grupo {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--espacio-1) var(--espacio-3);
	}

	.rotulo {
		font-weight: 600;
	}

	label {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		min-height: 44px;
	}

	.nota-opciones {
		flex-basis: 100%;
		margin: 0;
	}

	.notas-ingresos p {
		margin: 0;
	}

	.notas-ingresos p + p {
		margin-top: var(--espacio-2);
	}
</style>
