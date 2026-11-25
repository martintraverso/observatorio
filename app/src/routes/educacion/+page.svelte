<script lang="ts">
	// F4.8a3 (#226, AC-E32): catálogo de los cuadros del Anuario Estadístico de Educación (MEC) que tiene el sitio.
	import { resolve } from '$app/paths';
	import TablaDesplazable from '#lib/TablaDesplazable.svelte';
	import { NOMBRE_SITIO } from '#lib/sitio.ts';

	let { data } = $props();

	/** «2020–2024», o los años sueltos si falta alguno («2020, 2022–2024»). */
	function rango(anios: string[]): string {
		const n = anios.map(Number);
		const tramos: number[][] = [];
		for (const a of n) {
			const t = tramos.at(-1);
			if (t && a === t[t.length - 1] + 1) t.push(a);
			else tramos.push([a]);
		}
		return tramos.map((t) => (t.length > 1 ? `${t[0]}–${t.at(-1)}` : `${t[0]}`)).join(', ');
	}

	const TIPOS: Record<string, string> = {
		A: 'Por departamento',
		B: 'Nacional, por categoría',
		C: 'Nacional, por institución'
	};
</script>

<svelte:head>
	<title>Catálogo de educación · {NOMBRE_SITIO}</title>
</svelte:head>

<h1>Catálogo de educación</h1>
<p>
	Los cuadros del <em>Anuario Estadístico de Educación</em> del MEC que tiene el observatorio, con los años disponibles
	y dónde se ven. Los cuadros por departamento están en las fichas de cada departamento; los nacionales, en la ficha del
	país.
</p>

{#if data.cuadros.length === 0}
	<p class="info">Todavía no hay cuadros de educación publicados en el sitio.</p>
{:else}
	<TablaDesplazable etiqueta="Cuadros del anuario de educación" clase="tabla-apilada">
		<table>
			<caption class="visualmente-oculto">Cuadros del anuario de educación</caption>
			<thead>
				<tr>
					<th scope="col">Cuadro</th>
					<th scope="col">Título</th>
					<th scope="col">Tipo</th>
					<th scope="col">Años</th>
					<th scope="col">Dónde se ve</th>
				</tr>
			</thead>
			<tbody>
				{#each data.cuadros as c (c.cuadro)}
					<tr>
						<td data-etiqueta="Cuadro">{c.cuadro}</td>
						<td data-etiqueta="Título">{c.titulo}</td>
						<td data-etiqueta="Tipo">{TIPOS[c.tipo] ?? c.tipo}</td>
						<td data-etiqueta="Años">{rango(c.anios)}</td>
						<td data-etiqueta="Dónde se ve">
							{#if c.tipo === 'A'}
								<a href="{resolve('/territorio/[nivel]/[codigo]', { nivel: 'departamento', codigo: '01' })}#educacion">Fichas de departamento</a>
							{:else}
								<a href="{resolve('/territorio/[nivel]/[codigo]', { nivel: 'pais', codigo: 'UY' })}#educacion">Ficha del país</a>
							{/if}
							{#if c.mapa}
								· <a href="{resolve('/')}?indicador={c.mapa}">Mapa</a>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</TablaDesplazable>
{/if}

<style>
	/* AC-G5: los enlaces de la tabla son áreas táctiles de al menos 44 px */
	td a {
		display: inline-flex;
		align-items: center;
		min-height: var(--toque-min);
		font-weight: 600;
	}
</style>
