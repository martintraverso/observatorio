<script lang="ts">
	// Buscador de territorios (M5): combobox ARIA 1.2 con lista de sugerencias.
	// El índice (1,25 MB) se carga recién al usar el buscador, no al abrir la página (AC-G6).
	import { goto } from '$app/navigation';
	import { crearBuscador, type Buscador, type Resultado } from './busqueda.ts';
	import { cargarIndice, hrefFicha, type EntradaIndice } from './datos.ts';

	const ID_LISTA = 'buscar-sugerencias';
	const PLACEHOLDER = 'Buscar departamento, localidad o código INE';
	/** Si el texto largo no entra en el campo, este (AC-V16: nunca cortado). */
	const PLACEHOLDER_CORTO = 'Buscar territorio o código';
	let anchoCampo = $state(0);
	let lienzo: HTMLCanvasElement | null = null;
	let placeholder = $derived.by(() => (anchoCampo && !entra(PLACEHOLDER, anchoCampo) ? PLACEHOLDER_CORTO : PLACEHOLDER));

	/** Si el texto entra en el campo, con su letra y sin el relleno. */
	function entra(texto: string, ancho: number): boolean {
		if (!campo) return true;
		const cs = getComputedStyle(campo);
		const ctx = (lienzo ??= document.createElement('canvas')).getContext('2d');
		if (!ctx) return true;
		ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
		return ctx.measureText(texto).width <= ancho - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
	}

	let consulta = $state('');
	let abierto = $state(false);
	let activo = $state(-1);
	let estado = $state<'inactivo' | 'cargando' | 'listo' | 'error'>('inactivo');
	let buscador = $state<Buscador | null>(null);
	let campo: HTMLInputElement;

	let resultados: Resultado[] = $derived(buscador && consulta.trim().length >= 2 ? buscador.buscar(consulta) : []);
	let mostrarLista = $derived(abierto && consulta.trim().length >= 2);
	let anuncio = $derived.by(() => {
		if (!mostrarLista) return '';
		if (estado === 'cargando') return 'Cargando territorios…';
		if (estado === 'error') return 'No se pudo cargar el buscador.';
		if (resultados.length === 0) return `Sin resultados para «${consulta.trim()}».`;
		return resultados.length === 1 ? '1 resultado.' : `${resultados.length} resultados.`;
	});

	let carga: Promise<void> | null = null;

	/** Carga el índice una sola vez; quien la necesite (p. ej. Enter) puede esperarla. */
	function cargar(): Promise<void> {
		if (carga && estado !== 'error') return carga;
		estado = 'cargando';
		carga = cargarIndice()
			.then((indice) => {
				buscador = crearBuscador(indice);
				estado = 'listo';
			})
			.catch(() => {
				estado = 'error';
			});
		return carga;
	}

	function ir(t: EntradaIndice) {
		consulta = '';
		abierto = false;
		activo = -1;
		campo.blur();
		goto(hrefFicha(t));
	}

	function alEscribir() {
		abierto = true;
		activo = -1;
		cargar();
	}

	async function alTeclear(e: KeyboardEvent) {
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
			if (!resultados.length) return;
			e.preventDefault();
			abierto = true;
			const paso = e.key === 'ArrowDown' ? 1 : -1;
			activo = (activo + paso + resultados.length) % resultados.length;
		} else if (e.key === 'Enter') {
			e.preventDefault();
			// Si se apretó Enter antes de que termine de cargar el índice, esperarlo (no ignorar el Enter).
			if (!buscador) await cargar();
			if (activo >= 0 && resultados[activo]) return ir(resultados[activo].t);
			const exacto = buscador?.porCodigo(consulta); // AC-S2: código INE válido -> territorio
			if (exacto) return ir(exacto);
			if (resultados[0]) ir(resultados[0].t);
		} else if (e.key === 'Escape') {
			if (abierto && consulta) {
				abierto = false;
				activo = -1;
			} else {
				consulta = '';
			}
		}
	}
</script>

<form class="buscar" role="search" onsubmit={(e) => e.preventDefault()}>
	<label class="visualmente-oculto" for="buscar">{PLACEHOLDER}</label>
	<input
		bind:this={campo}
		bind:value={consulta}
		bind:clientWidth={anchoCampo}
		id="buscar"
		type="text"
		role="combobox"
		aria-autocomplete="list"
		aria-expanded={mostrarLista}
		aria-controls={ID_LISTA}
		aria-activedescendant={mostrarLista && activo >= 0 ? `${ID_LISTA}-${activo}` : undefined}
		{placeholder}
		autocomplete="off"
		spellcheck="false"
		onfocus={cargar}
		oninput={alEscribir}
		onkeydown={alTeclear}
		onblur={() => (abierto = false)}
	/>
	<ul id={ID_LISTA} role="listbox" aria-label="Territorios encontrados" hidden={!mostrarLista || !resultados.length}>
		{#each resultados as r, i (r.t.id)}
			<!-- El foco queda en el campo (aria-activedescendant); el clic no debe sacarlo. -->
			<li
				id="{ID_LISTA}-{i}"
				role="option"
				aria-selected={i === activo}
				onmousedown={(e) => e.preventDefault()}
				onclick={() => ir(r.t)}
				onkeydown={() => {}}
			>
				<span class="nombre">{r.t.nombre}</span>
				<span class="contexto">{r.contexto} · {r.t.codigo}</span>
			</li>
		{/each}
	</ul>
	<p class="visualmente-oculto" role="status" aria-live="polite">{anuncio}</p>
	{#if mostrarLista && !resultados.length}
		<p class="vacio">{anuncio}</p>
	{/if}
</form>

<style>
	.buscar {
		position: relative;
		flex: 1 1 260px;
		margin-left: auto;
	}

	input {
		width: 100%;
		min-height: var(--toque-min);
		padding: 0 var(--espacio-4);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		background: var(--fondo);
		font: inherit;
		color: var(--texto);
	}

	input::placeholder {
		color: var(--texto-suave);
	}

	ul,
	.vacio {
		position: absolute;
		top: calc(100% + 4px);
		left: 0;
		right: 0;
		z-index: 20;
		margin: 0;
		background: var(--tarjeta);
		border: 1px solid var(--borde);
		border-radius: var(--radio-m);
		box-shadow: var(--sombra);
	}

	ul {
		list-style: none;
		padding: var(--espacio-1);
		max-height: min(70vh, 480px);
		overflow-y: auto;
	}

	.vacio {
		padding: var(--espacio-3) var(--espacio-4);
		color: var(--texto-suave);
	}

	li {
		display: flex;
		flex-direction: column;
		justify-content: center;
		min-height: var(--toque-min);
		padding: var(--espacio-1) var(--espacio-3);
		border-radius: var(--radio-s);
		cursor: pointer;
	}

	li:hover,
	li[aria-selected='true'] {
		background: var(--azul-1);
	}

	li[aria-selected='true'] {
		box-shadow: inset 3px 0 0 var(--primario);
	}

	.nombre {
		font-weight: 600;
	}

	.contexto {
		font-size: var(--texto-s);
		color: var(--texto-suave);
	}
</style>
