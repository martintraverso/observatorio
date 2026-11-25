<script lang="ts">
	// F4.7b1 (#210, AC-E27, AC-E29): la educación de la ficha, una fila por cuadro del anuario del MEC con el valor
	// que lo resume en su último año, y el detalle (aperturas y notas del cuadro) plegado.
	import { publicado } from '../formato.ts';
	import { geometriaMiniSerie, type cuadrosEducacion } from './logica.ts';

	let { niveles }: { niveles: ReturnType<typeof cuadrosEducacion> } = $props();

	type Cuadro = ReturnType<typeof cuadrosEducacion>[number]['grupos'][number]['cuadros'][number];
	// F4.7b2 (#211, decisión del mantenedor): un gráfico chico por fila con la serie del valor que resume el cuadro.
	const W = 160;
	const H = 36;
	const M = 4;
	/** Lo que dice el gráfico, en texto (para lectores de pantalla). */
	function descripcion(c: Cuadro): string {
		const unidad = c.principal?.unidad ?? '';
		return (
			'Evolución: ' +
			c.tramos.map((t) => t.map((p) => `${p.anio}: ${publicado(p.valor)}${unidad ? ` ${unidad}` : ''}`).join('; ')).join(' — serie cortada — ')
		);
	}
</script>

{#each niveles as n (n.nivel)}
	<div class="nivel-educativo">
		<h3>{n.nivel}</h3>
		{#each n.grupos as g (g.grupo)}
			<h4>{g.grupo}</h4>
			<ul class="cuadros">
				{#each g.cuadros as c (c.cuadro)}
					<li class="cuadro">
						<p class="titulo">{c.titulo}</p>
						{#if c.principal}
							<p class="valor">
								{#if !/(^|· )Total$/.test(c.principal.etiqueta) && c.principal.etiqueta !== 'Tasa de promoción (total)'}
									<span class="suave">{c.principal.etiqueta}:</span>
								{/if}
								<strong>{publicado(c.principal.observacion.valor)} {c.principal.unidad}</strong>
								<span class="suave">· {c.anio}</span>
								{#if c.principal.calculado}<span class="calculado">calculado por el observatorio</span>{/if}
							</p>
						{:else}
							<p class="valor suave">Ver el detalle ({c.anio}).</p>
						{/if}
						{#if c.tramos.flat().length > 1}
							<figure class="mini-serie">
								<svg viewBox="0 0 {W} {H}" width={W} height={H} role="img" aria-label={descripcion(c)}>
									{#each geometriaMiniSerie(c.tramos, W, H, M) as t, i (i)}
										<polyline class="tramo" class:otro={t.tramo % 2 === 1} points={t.puntos.map((p) => `${p.cx},${p.cy}`).join(' ')} />
										{#each t.puntos as p (p.anio)}<circle class="punto" class:otro={t.tramo % 2 === 1} cx={p.cx} cy={p.cy} r="2.5" />{/each}
									{/each}
								</svg>
								<figcaption class="suave">
									{c.tramos[0][0].anio}–{c.tramos.at(-1)!.at(-1)!.anio}
									{#if c.cortes.length}<span class="corte">· Serie cortada: {c.cortes.join(' ')}</span>{/if}
								</figcaption>
							</figure>
						{/if}
						<p class="fuente suave">{c.fuente}</p>
						{#if c.aperturas.length || c.nota}
							<details>
								<summary>Detalle y notas del cuadro {c.cuadro}</summary>
								{#if c.aperturas.length}
									<ul class="aperturas">
										{#each c.aperturas as a (a.observacion.indicador)}
											<li>
												<span>{a.etiqueta}</span>
												<span class="num">
													{publicado(a.observacion.valor)}
													{a.unidad} · {c.anio}
													{#if a.calculado}<span class="calculado">calculado por el observatorio</span>{/if}
												</span>
											</li>
										{/each}
									</ul>
								{/if}
								{#if c.nota}<p class="nota">{c.nota}</p>{/if}
							</details>
						{/if}
					</li>
				{/each}
			</ul>
		{/each}
	</div>
{/each}

<style>
	h3 {
		font-size: var(--texto-m);
		margin: var(--espacio-4) 0 var(--espacio-2);
	}

	h4 {
		font-size: var(--texto-s);
		margin: var(--espacio-3) 0 var(--espacio-2);
	}

	.cuadros,
	.aperturas {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.cuadro {
		border-top: 1px solid var(--borde);
		padding: var(--espacio-2) 0;
	}

	.cuadro p {
		margin: 0 0 var(--espacio-1);
	}

	.titulo {
		font-weight: 600;
	}

	.fuente {
		font-size: var(--texto-s);
	}

	.mini-serie {
		margin: var(--espacio-1) 0;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--espacio-2);
	}

	.mini-serie svg {
		flex: none;
		overflow: visible;
	}

	.mini-serie figcaption {
		font-size: var(--texto-s);
	}

	.tramo {
		fill: none;
		stroke: var(--primario);
		stroke-width: 2;
	}

	.punto {
		fill: var(--primario);
	}

	/* el tramo de otro concepto (AC-E30): otro trazo, para que no se lea como una sola línea */
	.tramo.otro {
		stroke-dasharray: 4 3;
	}

	.punto.otro {
		fill: var(--tarjeta);
		stroke: var(--primario);
		stroke-width: 1.5;
	}

	.calculado {
		margin-left: var(--espacio-2);
		font-size: var(--texto-s);
		font-style: italic;
	}

	details summary {
		cursor: pointer;
		min-height: var(--toque-min);
		display: flex;
		align-items: center;
	}

	.aperturas li {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		gap: var(--espacio-2);
		padding: var(--espacio-1) 0;
		border-bottom: 1px dotted var(--borde);
		overflow-wrap: anywhere;
	}

	.num {
		text-align: right;
	}

	.nota {
		font-size: var(--texto-s);
		margin-top: var(--espacio-2);
	}
</style>
