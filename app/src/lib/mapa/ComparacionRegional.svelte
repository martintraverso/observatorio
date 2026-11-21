<script lang="ts">
	// F3.7c (AC-I20): lo que se publica por región (los ingresos de la ECH) no se pinta en el mapa: no hay datos por
	// departamento salvo Montevideo. En su lugar, una comparación chica entre el país, Montevideo y las regiones del
	// Interior para el indicador y el período elegidos. Solo valores publicados: nada se calcula.
	import { leerJson } from '#lib/datos.ts';
	import { numero } from '#lib/formato.ts';
	import { etiquetaPeriodo, filasComparacion, type IndicadorMapa } from './estado.ts';

	let { indicador, periodo }: { indicador: IndicadorMapa; periodo: string } = $props();

	type Valores = { indicadores: Record<string, Record<string, Record<string, number | null>>> };
	let valores = $state<Record<string, Valores | null>>({});
	$effect(() => {
		for (const nivel of ['pais', 'departamento', 'region']) {
			leerJson<Valores>(`valores/${nivel}.json`)
				.then((v) => (valores = { ...valores, [nivel]: v }))
				.catch(() => (valores = { ...valores, [nivel]: null }));
		}
	});
	let filas = $derived(filasComparacion(valores, indicador.codigo, periodo));
	let maximo = $derived(Math.max(1, ...filas.map((f) => f.valor ?? 0)));
</script>

<figure class="comparacion">
	<figcaption>
		<strong>{indicador.nombre}</strong>
		<span class="suave">{indicador.unidad} · {etiquetaPeriodo(periodo)}</span>
	</figcaption>
	<ul>
		{#each filas as f (f.nivel + f.codigo)}
			<li class:interior={f.nivel === 'region' && f.codigo !== 'interior'}>
				<span class="nombre">{f.nombre}</span>
				<span class="barra" aria-hidden="true"
					><span class="relleno" style:width="{f.valor === null ? 0 : (100 * f.valor) / maximo}%"></span></span
				>
				<span class="valor">{f.valor === null ? 'sin dato' : numero(f.valor, 0)}</span>
			</li>
		{/each}
	</ul>
	<p class="suave fuente">Fuente: INE, Encuesta Continua de Hogares. Cifras sujetas a revisión.</p>
</figure>

<style>
	.comparacion {
		margin: var(--espacio-2) 0 0;
		display: grid;
		gap: var(--espacio-2);
	}

	figcaption {
		display: grid;
		gap: 0.15rem;
	}

	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.4rem;
	}

	li {
		display: grid;
		grid-template-columns: minmax(8rem, 13rem) minmax(4rem, 1fr) auto;
		align-items: center;
		gap: var(--espacio-2);
	}

	li.interior .nombre {
		padding-left: 0.75rem;
	}

	.barra {
		height: 0.8rem;
		background: var(--fondo);
		border-radius: 4px;
		overflow: hidden;
	}

	.relleno {
		display: block;
		height: 100%;
		background: var(--primario);
	}

	.valor {
		font-variant-numeric: tabular-nums;
		text-align: right;
	}

	.fuente {
		margin: 0;
	}

	@media (max-width: 640px) {
		li {
			grid-template-columns: 1fr auto;
		}

		.barra {
			grid-column: 1 / -1;
			grid-row: 2;
		}
	}
</style>
