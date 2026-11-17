<script lang="ts">
	import type { Snippet } from 'svelte';

	// Contenedor de tablas anchas: se desplaza horizontalmente sin que se desplace la página (AC-G4)
	// y se puede enfocar con el teclado para desplazarlo (axe: scrollable-region-focusable).
	let { etiqueta, clase = '', children }: { etiqueta: string; clase?: string; children: Snippet } = $props();
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div class="tabla-scroll {clase}" role="region" aria-label={etiqueta} tabindex="0">
	{@render children()}
</div>
