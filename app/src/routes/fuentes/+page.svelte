<script lang="ts">
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import { NOMBRE_NIVEL } from '#lib/datos.ts';
	import { NOMBRE_SITIO } from '#lib/sitio.ts';

	let { data } = $props();
</script>

<svelte:head>
	<title>Fuentes · {NOMBRE_SITIO}</title>
</svelte:head>

<h1>Fuentes</h1>
<p>Los datos del observatorio salen de estas fuentes. Cada valor del sitio indica de qué archivo salió.</p>

<TablaDesplazable etiqueta="Fuentes de datos" clase="tarjeta">
	<table>
		<caption class="visualmente-oculto">Fuentes de datos</caption>
		<thead>
			<tr>
				<th scope="col">Fuente</th>
				<th scope="col">Temas</th>
				<th scope="col">Nivel más detallado</th>
				<th scope="col">Frecuencia</th>
				<th scope="col">Estado</th>
			</tr>
		</thead>
		<tbody>
			{#each data.fuentes as f (f.id)}
				<tr>
					<td>
						<a href={f.pagina}>{f.nombre}</a><br />
						<span class="suave">{f.organismo}</span>
					</td>
					<td>{f.temas.join(', ')}</td>
					<td>{NOMBRE_NIVEL[f.nivel_mas_detallado] ?? f.nivel_mas_detallado}</td>
					<td>{f.frecuencia}</td>
					<td><span class="estado">{f.estado}</span></td>
				</tr>
			{/each}
		</tbody>
	</table>
</TablaDesplazable>

<style>
	td a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
	}

	.estado {
		display: inline-block;
		padding: 0 var(--espacio-2);
		border-radius: var(--radio-s);
		background: var(--azul-1);
		border: 1px solid var(--borde);
	}
</style>
