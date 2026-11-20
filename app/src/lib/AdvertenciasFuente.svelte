<script lang="ts">
	// AC-L26: las advertencias de la fuente (texto del INE, campo `advertencias` del registro) junto a sus datos.
	// AC-V23: un resumen de 1–2 líneas (la primera advertencia) y la lista completa plegada.
	let { fuente, advertencias, resumen = '' }: { fuente: string; advertencias: string[]; resumen?: string } = $props();
	// el resumen de la fuente (nombra todos los temas); si no tiene, la primera advertencia
	let textoResumen = $derived(resumen || advertencias[0]);
	let conLista = $derived(resumen ? advertencias.length > 0 : advertencias.length > 1);
	const id = $props.id();
</script>

{#if advertencias.length}
	<!-- advertencias metodológicas de la fuente: información, no alarma (AC-V22) -->
	<div class="advertencias info" role="group" aria-labelledby="{id}-titulo">
		<p class="titulo" id="{id}-titulo">Advertencias del INE (resumidas) sobre estos datos · {fuente}</p>
		<p class="resumen">{textoResumen}</p>
		{#if conLista}
			<details>
				<summary>Ver todas las advertencias ({advertencias.length})</summary>
				<ul>
					{#each advertencias as a (a)}<li>{a}</li>{/each}
				</ul>
			</details>
		{/if}
	</div>
{/if}

<style>
	.advertencias {
		padding: var(--espacio-2) var(--espacio-3);
		font-size: var(--texto-s);
	}

	.titulo {
		margin: 0;
		font-weight: 600;
	}

	/* sin recortar: el resumen nombra todos los temas (en escritorio ocupa 1–2 líneas) */
	.resumen {
		margin: var(--espacio-1) 0 0;
	}

	summary {
		cursor: pointer;
		font-weight: 600;
		min-height: var(--toque-min);
		display: flex;
		align-items: center;
	}

	ul {
		margin: 0;
		padding-left: var(--espacio-4);
	}

	li + li {
		margin-top: var(--espacio-1);
	}
</style>
