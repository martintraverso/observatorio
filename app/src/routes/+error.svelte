<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { NOMBRE_SITIO } from '#lib/sitio.ts';

	let titulo = $derived(page.status === 404 ? 'Página no encontrada' : 'Algo salió mal');
</script>

<svelte:head>
	<title>{titulo} · {NOMBRE_SITIO}</title>
</svelte:head>

<h1>{titulo}</h1>
<p>{page.error?.message ?? 'No pudimos mostrar esta página.'}</p>
<p>
	Podés volver al <a href={resolve('/')}>mapa</a> o buscar el territorio en las
	<a href={resolve('/fichas')}>fichas</a>.
</p>
