<script lang="ts">
	// AC-L26: las advertencias de la fuente (texto del INE, campo `advertencias` del registro) junto a sus datos.
	let { fuente, advertencias }: { fuente: string; advertencias: string[] } = $props();
</script>

{#if advertencias.length}
	<details class="advertencias" open>
		<summary>Advertencias del INE (resumidas) sobre estos datos · {fuente}</summary>
		<ul>
			{#each advertencias as a (a)}<li>{a}</li>{/each}
		</ul>
	</details>
{/if}

<style>
	.advertencias {
		background: var(--aviso-fondo);
		border: 1px solid var(--aviso-borde);
		color: var(--aviso-texto);
		border-radius: var(--radio-m);
		padding: var(--espacio-2) var(--espacio-3);
		font-size: var(--texto-s);
	}

	summary {
		cursor: pointer;
		font-weight: 600;
		min-height: var(--toque-min);
		display: flex;
		align-items: center;
	}

	ul {
		margin: var(--espacio-2) 0 0;
		padding-left: var(--espacio-4);
	}

	li + li {
		margin-top: var(--espacio-1);
	}
</style>
