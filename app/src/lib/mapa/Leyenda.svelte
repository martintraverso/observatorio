<script lang="ts">
	// Leyenda de la coropleta (AC-M1, AC-G2): clases con unidad, fuente y período.
	import { COLOR_SIN_DATO, coloresClases } from './colores.ts';
	import { etiquetasLeyenda, type Clases } from './estado.ts';

	let {
		titulo,
		unidad,
		clases,
		fuente,
		periodo,
		hayEstimados = false
	}: {
		titulo: string;
		unidad: string;
		clases: Clases | null;
		fuente: string;
		periodo: string;
		hayEstimados?: boolean;
	} = $props();

	let etiquetas = $derived(clases ? etiquetasLeyenda(clases) : []);
	let colores = $derived(coloresClases(etiquetas.length));
</script>

<section class="leyenda" aria-label="Leyenda">
	<h2>{titulo} <span class="unidad">({unidad})</span></h2>
	<ul>
		{#each etiquetas as e, i (e)}
			<li><span class="muestra" style:background={colores[i]}></span>{e}</li>
		{/each}
		<li><span class="muestra" style:background={COLOR_SIN_DATO}></span>Sin dato</li>
	</ul>
	<p class="fuente">Fuente: {fuente} · {periodo}</p>
	{#if hayEstimados}<p class="fuente">Incluye valores estimados.</p>{/if}
</section>

<style>
	.leyenda {
		background: var(--tarjeta);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		padding: var(--espacio-3);
		font-size: var(--texto-s);
		max-width: 320px;
	}

	h2 {
		font-size: var(--texto-s);
		font-family: var(--fuente-texto);
		font-weight: 600;
		margin: 0 0 var(--espacio-2);
	}

	.unidad {
		font-weight: 400;
		color: var(--texto-suave);
	}

	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 2px;
	}

	li {
		display: flex;
		align-items: center;
		gap: var(--espacio-2);
		font-variant-numeric: tabular-nums;
	}

	.muestra {
		width: 18px;
		height: 12px;
		border-radius: 3px;
		border: 1px solid rgb(0 0 0 / 0.08);
		flex: none;
	}

	.fuente {
		margin: var(--espacio-2) 0 0;
		color: var(--texto-suave);
		font-size: var(--texto-xs);
	}
</style>
