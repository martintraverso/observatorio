<script lang="ts">
	// Panel del territorio seleccionado (AC-M3, AC-M4, AC-G2).
	import { descargarCsv } from '../csv.ts';
	import { hrefFicha, NOMBRE_NIVEL, type Ficha, type Observacion } from '../datos.ts';
	import { publicado } from '../formato.ts';
	import { etiquetaPeriodo, fuenteCorta } from './estado.ts';
	import AdvertenciasFuente from '../AdvertenciasFuente.svelte';
	import MiniMapa from './MiniMapa.svelte';

	let {
		ficha,
		indicador,
		periodo,
		totalPais = 'nunca',
		oncerrar
	}: {
		ficha: Ficha;
		indicador: string;
		periodo: string;
		/** Si la fuente publica el total del país en este período, solo en otros o nunca (estado.totalDelPais). */
		totalPais?: 'periodo' | 'otros' | 'nunca';
		oncerrar: () => void;
	} = $props();

	let principal = $derived(ficha.observaciones.find((o) => o.indicador === indicador && o.periodo === periodo) ?? null);
	let otros = $derived(
		ficha.observaciones.filter((o) => o !== principal && o.periodo === periodo).slice(0, 3)
	);

	function fuente(o: Observacion): string {
		const c = ficha.capturas[o.captura_id];
		const f = c && ficha.fuentes[c.fuente_id];
		return f ? fuenteCorta(f) : o.captura_id;
	}
	const ind = (o: Observacion) => ficha.indicadores[o.indicador];
	const refFuente = (o: Observacion) => ficha.fuentes[ficha.capturas[o.captura_id]?.fuente_id];
</script>

<article class="panel" aria-labelledby="panel-titulo">
	<header>
		<div>
			<h2 id="panel-titulo">{ficha.nombre}</h2>
			<p class="suave">{NOMBRE_NIVEL[ficha.nivel]} · Código INE {ficha.codigo}</p>
		</div>
		<button type="button" class="cerrar" onclick={oncerrar} aria-label="Cerrar el panel de {ficha.nombre}">✕</button>
	</header>

	<div class="ubicacion">
		<MiniMapa nombre={ficha.nombre} depto={ficha.depto} nivel={ficha.nivel} bbox={ficha.bbox} />
	</div>

	{#if principal}
		<div class="principal">
			<p class="etiqueta">{ind(principal)?.nombre} · {etiquetaPeriodo(principal.periodo)}</p>
			<p class="valor">
				{publicado(principal.valor)} <span class="unidad">{ind(principal)?.unidad}</span>
				{#if principal.es_estimado}<span class="estimado">estimado</span>{/if}
			</p>
			<p class="suave fuente">Fuente: {fuente(principal)}</p>
			<!-- AC-V11: una línea corta. El total es el que publica la fuente; nunca se calcula sumando territorios. -->
			<p class="suave fuente">
				{#if totalPais === 'periodo'}
					Total del país: en la <a href={hrefFicha({ nivel: 'pais', codigo: 'UY' })}>ficha de Uruguay</a>.
				{:else if totalPais === 'otros'}
					Total del país: no publicado para este período (sí para otros, en la <a
						href={hrefFicha({ nivel: 'pais', codigo: 'UY' })}>ficha de Uruguay</a
					>).
				{:else}
					Total del país: no publicado por la fuente.
				{/if}
			</p>
			<AdvertenciasFuente fuente={refFuente(principal)?.nombre ?? ''} advertencias={refFuente(principal)?.advertencias ?? []} />
		</div>
	{:else}
		<p class="aviso">Este territorio no tiene datos de este indicador para {etiquetaPeriodo(periodo)}.</p>
	{/if}

	{#if otros.length}
		<h3>Otros datos</h3>
		<dl class="otros">
			{#each otros as o (o.indicador + o.periodo)}
				<div>
					<dt>{ind(o)?.nombre} ({etiquetaPeriodo(o.periodo)})</dt>
					<dd>
						{publicado(o.valor)}
						{ind(o)?.unidad}{#if o.es_estimado}<span class="estimado">estimado</span>{/if}
					</dd>
				</div>
			{/each}
		</dl>
		<!-- la fuente, una sola vez: solo si los otros datos son de otra fuente que el principal (AC-V11) -->
		{#if !principal || fuente(otros[0]) !== fuente(principal)}<p class="suave fuente">Fuente: {fuente(otros[0])}</p>{/if}
	{/if}

	<div class="acciones">
		<a class="boton primario" href={hrefFicha(ficha)}>Ver ficha completa</a>
		<button type="button" class="boton" onclick={() => descargarCsv(ficha)}>Descargar CSV</button>
	</div>
</article>

<style>
	.panel {
		display: grid;
		gap: var(--espacio-3);
	}

	header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--espacio-2);
	}

	h2 {
		margin: 0;
	}

	header p {
		margin: var(--espacio-1) 0 0;
		font-size: var(--texto-s);
	}

	h3 {
		font-size: var(--texto-m);
		margin: 0;
	}

	.cerrar {
		min-width: var(--toque-min);
		min-height: var(--toque-min);
		border: 1px solid var(--borde);
		border-radius: var(--radio-s);
		background: var(--tarjeta);
		font-size: var(--texto-m);
		cursor: pointer;
	}

	.ubicacion {
		max-width: 220px;
	}

	@media (max-width: 900px) {
		/* En la hoja inferior, el mini-mapa chico para que se siga viendo el mapa. */
		.ubicacion {
			max-width: 110px;
		}
	}

	.principal p {
		margin: 0;
	}

	.etiqueta {
		font-size: var(--texto-s);
		font-weight: 600;
	}

	.valor {
		font-family: var(--fuente-titulos);
		font-size: var(--texto-xl);
		font-weight: 700;
	}

	.unidad {
		font-size: var(--texto-m);
		font-weight: 500;
		color: var(--texto-suave);
	}

	.fuente {
		font-size: var(--texto-xs);
		margin-top: var(--espacio-1) !important;
	}

	.otros {
		margin: 0;
		display: grid;
		gap: var(--espacio-1);
	}

	.otros div {
		display: flex;
		justify-content: space-between;
		gap: var(--espacio-2);
		border-bottom: 1px solid var(--borde);
		padding: var(--espacio-1) 0;
		font-size: var(--texto-s);
	}

	.otros dd {
		margin: 0;
		font-variant-numeric: tabular-nums;
		text-align: right;
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

	/* los botones del mismo ancho, uno debajo del otro: en 330 px dos columnas cortaban el texto (AC-V11) */
	.acciones {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--espacio-2);
	}

	.acciones .boton {
		justify-content: center;
		text-align: center;
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

	.boton.primario:hover {
		background: var(--primario-hover);
	}
</style>
