// M10.0 (#78): controles de calidad visual sobre el sitio construido, en las cuatro vistas
// (proyectos `visual-*` de playwright.config.ts). Criterios: docs/ACCEPTANCE_CRITERIA_UI.md.
//
// Los problemas que el `main` todavía tiene están marcados con `pendiente(...)`: el test se
// espera que falle (test.fail) y se pone rojo cuando el problema se corrige, para que la
// historia que lo corrige saque la marca. Así el arnés prueba que detecta cada problema.
import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { nivelesOfrecidos } from '../../src/lib/mapa/estado.ts';
import { abrirOpciones, detectarDesbordes, esperarQuieta, revisarSegmentado, sinTextoInterno } from './ayudas';

type Territorio = { nivel: string; codigo: string; nombre: string; depto: string };
const indice = JSON.parse(readFileSync('build/datos-web/territorios_index.json', 'utf-8')) as Territorio[];
const fuentes = JSON.parse(readFileSync('build/datos-web/fuentes.json', 'utf-8')) as { id: string }[];
const indicadores = JSON.parse(readFileSync('build/datos-web/indicadores.json', 'utf-8')) as Parameters<typeof nivelesOfrecidos>[0][];
const catalogo = JSON.parse(readFileSync('build/datos-web/niveles.json', 'utf-8')) as Parameters<typeof nivelesOfrecidos>[1];
// M11.4: el selector muestra los niveles del indicador elegido (al abrir, el primero)
const NIVELES_INICIO = nivelesOfrecidos(indicadores[0], catalogo);

// Tacuarembó es la ficha de referencia de AC-V18; con el fixture (sin Tacuarembó), Flores.
const DEPTO = indice.find((t) => t.nivel === 'departamento' && t.codigo === '18') ?? indice.find((t) => t.nivel === 'departamento' && t.codigo === '07')!;
const SEGMENTO = indice.find((t) => t.nivel === 'segmento' && t.depto === DEPTO.depto)!;
const fichaDepto = JSON.parse(readFileSync(`build/datos-web/fichas/departamento/${DEPTO.codigo}.json`, 'utf-8')) as {
	capturas: Record<string, { fuente_id: string }>;
};
const capturasDepto = Object.values(fichaDepto.capturas);
const fuentesDepto = new Set(capturasDepto.map((c) => c.fuente_id));


/** Vista del proyecto: 'visual-firefox-768' → '768'. */
const vista = (proyecto: string) => proyecto.split('-').at(-1)!;

const RUTAS: { ruta: string; nombre: string }[] = [
	{ ruta: '', nombre: 'Mapa' },
	{ ruta: 'fichas', nombre: 'Fichas' },
	{ ruta: `territorio/departamento/${DEPTO.codigo}`, nombre: `Ficha departamento (${DEPTO.nombre})` },
	{ ruta: `territorio/segmento/${SEGMENTO.codigo}`, nombre: 'Ficha segmento' },
	{ ruta: 'fuentes', nombre: 'Fuentes' },
	...fuentes.map((f) => ({ ruta: `fuentes/${f.id}`, nombre: `Fuente ${f.id}` })),
	{ ruta: 'datos', nombre: 'Datos' }
];

/** Problema conocido del `main`: el test tiene que fallar hasta que la historia indicada lo corrija. */
function pendiente(condicion: boolean, historia: string) {
	test.fail(condicion, `problema conocido, lo corrige ${historia}`);
}

for (const { ruta, nombre } of RUTAS) {
	test.describe(nombre, () => {
		test('AC-V5: ningún texto desborda ni queda recortado', async ({ page }) => {
			await page.goto(ruta);
			expect(await detectarDesbordes(page)).toEqual([]);
		});

		test('AC-V19: sin textos internos del mantenedor', async ({ page }) => {
			await page.goto(ruta);
			expect(await sinTextoInterno(page)).toEqual([]);
		});
	});
}

const NIVEL_TERRITORIAL = 'fieldset:has(> legend:text-is("Nivel territorial"))';

// AC-N10 (M11.4): de 1 a 6 opciones sin mover los controles de arriba ni cambiar el ancho del panel. Con 1, la app
// muestra el texto fijo «Nivel: …» (AC-N6); ningún indicador activo ofrece un solo nivel, así que se arma igual
// que el componente (p.nivel-unico) en lugar de la lista.
for (const cantidad of [1, 2, 3, 4, 5, 6]) {
	test(`AC-V1 y AC-N10: el selector «Nivel territorial» con ${cantidad} niveles: una fila o una lista vertical, sin cortes`, async ({ page }) => {
		await page.goto('');
		await abrirOpciones(page);
		await expect(page.locator(NIVEL_TERRITORIAL).getByRole('radio')).toHaveCount(NIVELES_INICIO.length);
		await page.locator(NIVEL_TERRITORIAL).evaluate((g) => g.setAttribute('data-prueba', 'nivel'));
		const SELECTOR = '[data-prueba="nivel"]';
		/** Ancho del panel y posición de los controles de arriba del selector, relativa a su primera opción de control. */
		const arriba = () =>
			page.locator(SELECTOR).evaluate((g) => {
				const panel = g.closest('aside')!;
				// los controles del mapa (en celular, la hoja de opciones; la barra de resumen queda fuera)
				const controles = g.closest('#controles-mapa')!;
				// referencia: el indicador (arriba del selector), para que el scroll de la hoja no cuente como movimiento
				const ref = controles.querySelector('fieldset:has(> legend)')!.getBoundingClientRect().y;
				const y0 = g.getBoundingClientRect().y;
				return {
					ancho: panel.clientWidth,
					selector: Math.round(y0 - ref),
					controles: [...controles.querySelectorAll('label, legend, select, button')]
						.filter((el) => !g.contains(el) && el.getBoundingClientRect().width > 1 && el.getBoundingClientRect().y < y0)
						.map((el) => [Math.round(el.getBoundingClientRect().x), Math.round(el.getBoundingClientRect().y - ref)])
				};
			});
		const antes = await arriba();
		// Con otra cantidad de niveles que la del build: se copian o se quitan opciones (el diseño no depende de cuántas haya).
		await page.locator(SELECTOR).evaluate((g, n) => {
			if (n === 1) {
				const p = document.createElement('p');
				// con la clase de estilos del componente (Svelte), como la pinta la página
				p.className = ['nivel-unico', ...[...g.classList].filter((c) => c.startsWith('svelte-'))].join(' ');
				p.setAttribute('data-prueba', 'nivel');
				p.textContent = 'Nivel: Departamento';
				g.replaceWith(p);
				return;
			}
			const opciones = [...g.querySelectorAll('label')];
			opciones.slice(n).forEach((o) => o.remove());
			for (let i = opciones.length; i < n; i++) {
				const copia = opciones[1].cloneNode(true) as HTMLElement;
				copia.querySelector('input')!.name = 'nivel-de-prueba';
				opciones[0].parentElement!.append(copia);
			}
		}, cantidad);
		if (cantidad > 1) {
			await expect(page.locator(NIVEL_TERRITORIAL).locator('label')).toHaveCount(cantidad);
			expect(await revisarSegmentado(page, NIVEL_TERRITORIAL)).toEqual([]);
		}
		expect(await detectarDesbordes(page)).toEqual([]);
		expect(await arriba()).toEqual(antes);
		// la página nunca se desplaza de costado (390 px incluido)
		expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
	});
}

test('AC-V2: el municipio dice «Municipio» con la ayuda «Solo Montevideo»', async ({ page }) => {
	// M11.4: el selector es del indicador elegido; se abre uno que se publica por municipio (Trabajo), no el de inicio
	const conMunicipio = (indicadores as unknown as { codigo: string; niveles: string[]; niveles_mapa?: string[] }[]).find((i) =>
		(i.niveles_mapa ?? i.niveles).includes('municipio_mvd')
	);
	test.skip(!conMunicipio, 'el build no trae datos por municipio (fixture)');
	await page.goto(`?indicador=${conMunicipio!.codigo}&nivel=departamento`);
	const opcion = page.locator(NIVEL_TERRITORIAL).locator('label', { has: page.locator('input[value="municipio_mvd"]') });
	await expect(opcion.locator('.nombre')).toHaveText('Municipio');
	await expect(opcion.locator('.ayuda')).toHaveText('Solo Montevideo');
});

/** Ancho del panel izquierdo y posición de cada control visible, relativa al contenido del panel (sin contar su scroll). */
async function medirPanel(page: import('@playwright/test').Page) {
	return page.locator('aside.opciones').evaluate((panel) => {
		const p = panel.getBoundingClientRect();
		return {
			ancho: panel.clientWidth,
			controles: [...panel.querySelectorAll('label, legend, select')]
				.filter((el) => el.getBoundingClientRect().width > 1) // sin los ocultos ni los «solo para lectores de pantalla»
				.map((el) => {
					const r = el.getBoundingClientRect();
					return { texto: (el.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, 30), x: Math.round(r.x - p.x), y: Math.round(r.y - p.y + panel.scrollTop) };
				})
		};
	});
}

/** Posición vertical de un control relativa al contenido del panel. */
const yEnPanel = (control: import('@playwright/test').Locator) =>
	control.evaluate((el) => {
		const panel = el.closest('aside')!;
		return Math.round(el.getBoundingClientRect().y - panel.getBoundingClientRect().y + panel.scrollTop);
	});

test('AC-V3: cambiar tema, indicador o nivel no cambia el ancho del panel ni mueve los controles de arriba', async ({ page }, info) => {
	test.skip(!['1440', '1024'].includes(vista(info.project.name)), 'el panel lateral existe a 1440 y 1024 px');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
	await esperarQuieta(page);
	const panel = page.locator('aside.opciones');
	const gutter = await panel.evaluate((p) => getComputedStyle(p).scrollbarGutter);
	expect(gutter).toContain('stable');

	// #249: la lista tiene un ítem por familia; el cambio de indicador se prueba en un tema sin niveles educativos con
	// al menos dos familias (con los datos completos, Trabajo). Si los datos no tienen ninguno, ese paso no se prueba.
	const familias = indicadores as unknown as { tema: string; grupo?: string; mapa?: boolean; familia?: string; codigo: string }[];
	const porTema = new Map<string, number>();
	for (const i of familias)
		if (i.mapa !== false && !i.grupo && (i.familia ?? i.codigo) === i.codigo) porTema.set(i.tema, (porTema.get(i.tema) ?? 0) + 1);
	const temaVarios = [...porTema].find(([, n]) => n >= 2)?.[0];
	// `cambia`: el clic tiene que cambiar el estado en la URL (si no, el paso no probaría nada).
	const clics = [
		{ control: panel.getByRole('group', { name: 'Tema' }).getByText('Población', { exact: true }), cambia: false },
		...(temaVarios
			? [
					{ control: panel.getByRole('group', { name: 'Tema' }).getByText(temaVarios, { exact: true }), cambia: false },
					{ control: panel.getByRole('group', { name: 'Indicador' }).locator('label.indicador:not(.activo)').first(), cambia: true },
					{ control: panel.getByRole('group', { name: 'Tema' }).getByText('Población', { exact: true }), cambia: false }
				]
			: []),
		{ control: panel.getByRole('group', { name: 'Nivel territorial' }).locator('label').last(), cambia: true },
		{ control: panel.getByRole('group', { name: 'Nivel territorial' }).locator('label').first(), cambia: true }
	];
	for (const { control, cambia } of clics) {
		const yControl = await yEnPanel(control);
		const antes = await medirPanel(page);
		const url = page.url();
		await control.click();
		if (cambia) await expect(page).not.toHaveURL(url);
		await esperarQuieta(page);
		const despues = await medirPanel(page);
		expect(despues.ancho, 'ancho del panel').toBe(antes.ancho);
		const arriba = (m: typeof antes) => m.controles.filter((c) => c.y < yControl - 1);
		expect(arriba(despues), `controles arriba de «${await control.textContent()}»`).toEqual(arriba(antes));
	}
});

test('AC-V4: a 1440×900 la leyenda se ve entera sin hacer scroll', async ({ page }, info) => {
	test.skip(vista(info.project.name) !== '1440', 'el criterio es a 1440×900');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
	await esperarQuieta(page);
	const leyenda = page.getByRole('region', { name: 'Leyenda' }).locator('visible=true');
	await expect(leyenda).toBeVisible();
	const caja = (await leyenda.boundingBox())!;
	expect(caja.y).toBeGreaterThanOrEqual(0);
	expect(caja.y + caja.height).toBeLessThanOrEqual(900);
	expect(caja.x + caja.width).toBeLessThanOrEqual(1440);
	expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test('AC-V17: la fuente y el período de la leyenda no repiten un año', async ({ page }) => {
	// #222: con la educación activa son unos 120 indicadores por departamento (1 minuto en local)
	test.setTimeout(240_000);
	// Cada indicador por departamento, entrando por URL y esperando su propia leyenda.
	// los que se publican por región (ingresos) no tienen leyenda: se muestran como comparación (AC-I20)
	// solo los de la lista del mapa (de educación, las tasas calculadas, #213)
	for (const i of indicadores.filter((x) => (x as { mapa?: boolean }).mapa !== false && (x.niveles_mapa ?? x.niveles).includes('departamento')) as unknown as { codigo: string; nombre: string }[]) {
		await page.goto(`?indicador=${i.codigo}&nivel=departamento`);
		const leyenda = page.getByRole('region', { name: 'Leyenda' }).locator('visible=true');
		await expect(leyenda.getByRole('heading')).toContainText(i.nombre);
		const texto = (await leyenda.locator('.fuente').first().textContent()) ?? '';
		const anios = texto.match(/\b(19|20)\d{2}\b/g) ?? [];
		expect(new Set(anios).size, texto).toBe(anios.length);
	}
});

test(`AC-V18: «Fuentes de esta ficha» muestra una entrada por fuente (${DEPTO.nombre})`, async ({ page }) => {
	await page.goto(`territorio/departamento/${DEPTO.codigo}`);
	const entradas = page.locator('#fuentes ul.fuentes > li');
	await expect(entradas).toHaveCount(fuentesDepto.size);
	for (const id of fuentesDepto) {
		const entrada = entradas.filter({ has: page.locator(`a[href$="/fuentes/${id}"]`) });
		await expect(entrada).toHaveCount(1);
		await expect(entrada).toContainText('Licencia:');
		await expect(entrada).toContainText('Última captura procesada el');
		const n = capturasDepto.filter((c) => c.fuente_id === id).length;
		// la lista de archivos, plegada
		const archivos = entrada.locator('details');
		await expect(archivos.locator('summary')).toHaveText(n === 1 ? 'Ver el archivo' : `Ver los ${n} archivos`);
		await expect(archivos).not.toHaveAttribute('open');
		await expect(archivos.locator('li').first()).toBeHidden();
	}
	// la licencia aparece una vez por fuente, no una por archivo
	expect(await page.locator('#fuentes').getByText('Licencia:').count()).toBe(fuentesDepto.size);
});

test(`AC-V18: largo de la ficha de Tacuarembó`, async ({ page }, info) => {
	const maximo = ({ '1440': 6000, '390': 15000 } as Record<string, number>)[vista(info.project.name)];
	test.skip(!maximo, 'el criterio fija el largo a 1440 y a 390 px');
	test.skip(DEPTO.codigo !== '18', 'el build no trae Tacuarembó (fixture)');
	await page.goto(`territorio/departamento/${DEPTO.codigo}`);
	await esperarQuieta(page);
	const alto = await page.evaluate(() => document.documentElement.scrollHeight);
	expect(alto, `${alto} px`).toBeLessThanOrEqual(maximo!);
});

test('AC-V14: en celular y tableta el encabezado tiene como máximo 2 filas (≤ 120 px)', async ({ page }, info) => {
	test.skip(!['768', '390'].includes(vista(info.project.name)), 'el criterio es para celular y tableta');
	await page.goto('');
	await esperarQuieta(page);
	const { alto, filas } = await page.locator('header.encabezado').evaluate((h) => {
		const partes = [h.querySelector('.marca'), h.querySelector('nav'), h.querySelector('form.buscar')].map((e) => e!.getBoundingClientRect());
		const tops: number[] = [];
		for (const r of partes) if (!tops.some((t) => Math.abs(t - r.top) < r.height / 2)) tops.push(r.top);
		return { alto: h.getBoundingClientRect().height, filas: tops.length };
	});
	expect(alto).toBeLessThanOrEqual(120);
	expect(filas).toBeLessThanOrEqual(2);
	// el nombre del sitio sigue en el enlace para lectores de pantalla
	await expect(page.getByRole('link', { name: 'Observatorio Uruguay' })).toBeVisible();
});

test('AC-V16: el texto de ayuda de la búsqueda nunca queda cortado', async ({ page }) => {
	await page.goto('');
	await esperarQuieta(page);
	const { texto, entra } = await page.locator('#buscar').evaluate((i: HTMLInputElement) => {
		const cs = getComputedStyle(i);
		const ctx = document.createElement('canvas').getContext('2d')!;
		ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
		return { texto: i.placeholder, entra: ctx.measureText(i.placeholder).width <= i.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) };
	});
	expect(entra, texto).toBe(true);
	// el nombre accesible del campo sigue siendo el completo
	await expect(page.getByRole('combobox', { name: 'Buscar departamento, localidad o código INE' })).toBeVisible();
});

test('AC-V15: en celular los chips de temas no muestran barra de desplazamiento y se desvanecen en el borde', async ({ page }, info) => {
	test.skip(!['768', '390'].includes(vista(info.project.name)), 'la fila desplazable es de celular y tableta');
	await page.goto('');
	const estilo = await page.locator('.chips').evaluate((c) => {
		const cs = getComputedStyle(c);
		return { barra: cs.scrollbarWidth, mascara: cs.maskImage || (cs as unknown as Record<string, string>).webkitMaskImage };
	});
	expect(estilo.barra).toBe('none');
	expect(estilo.mascara).toContain('linear-gradient');
});

test('AC-V14 / AC-G5: a 320 px el logo es un área táctil de 44 px y la navegación no lo pisa', async ({ page }, info) => {
	test.skip(vista(info.project.name) !== '390', 'se prueba una vez, en la vista de celular');
	await page.setViewportSize({ width: 320, height: 700 });
	await page.goto('');
	await esperarQuieta(page);
	const r = await page.evaluate(() => {
		const marca = document.querySelector('header .marca')!.getBoundingClientRect();
		const primero = document.querySelector('header nav a')!.getBoundingClientRect();
		const alto = document.querySelector('header.encabezado')!.getBoundingClientRect().height;
		return { marca: { ancho: marca.width, alto: marca.height, derecha: marca.right }, primero: primero.left, alto, scroll: document.documentElement.scrollWidth - document.documentElement.clientWidth };
	});
	expect(r.marca.ancho).toBeGreaterThanOrEqual(44);
	expect(r.marca.alto).toBeGreaterThanOrEqual(44);
	expect(r.marca.derecha).toBeLessThanOrEqual(r.primero);
	expect(r.alto).toBeLessThanOrEqual(120);
	expect(r.scroll).toBe(0);
	expect(await detectarDesbordes(page)).toEqual([]);
});

test('AC-V15: el chip con el foco de teclado no queda bajo el desvanecido', async ({ page }, info) => {
	test.skip(vista(info.project.name) !== '390', 'la fila desplazable se prueba en celular');
	await page.goto('');
	await abrirOpciones(page);
	const temas = page.getByRole('group', { name: 'Tema' }).getByRole('radio');
	await temas.first().focus();
	for (let i = 1; i < (await temas.count()); i++) {
		await page.keyboard.press('ArrowRight');
		// la fila de temas (la primera; con Educación hay otra con los niveles educativos)
		const { chip, fila, mascara } = await page.locator('.chips').first().evaluate((c) => {
			const enfocado = c.querySelector('label:has(input:focus)')!.getBoundingClientRect();
			const cs = getComputedStyle(c);
			return { chip: enfocado, fila: c.getBoundingClientRect(), mascara: cs.maskImage || (cs as unknown as Record<string, string>).webkitMaskImage };
		});
		// o no hay máscara mientras hay foco, o el chip termina antes de la zona desvanecida
		const visible = mascara === 'none' || chip.right <= fila.right - 48;
		expect(visible).toBe(true);
		expect(chip.right).toBeLessThanOrEqual(fila.right);
		expect(chip.left).toBeGreaterThanOrEqual(fila.left);
	}
});

test('AC-V25: en celular la ficha no tiene KPIs cortados, tablas de indicadores con scroll ni barra de secciones visible', async ({ page }, info) => {
	test.skip(vista(info.project.name) !== '390', 'el criterio es a 390 px');
	await page.goto(`territorio/departamento/${DEPTO.codigo}`);
	await esperarQuieta(page);
	// KPI en una sola línea
	const kpis = await page.locator('.kpis dd').evaluateAll((dds) =>
		dds.map((dd) => ({ texto: dd.textContent?.trim(), alto: dd.getBoundingClientRect().height, linea: parseFloat(getComputedStyle(dd).lineHeight) }))
	);
	expect(kpis.length).toBeGreaterThan(0);
	for (const k of kpis) expect(k.alto, k.texto).toBeLessThan(k.linea * 1.5);
	// tablas de indicadores apiladas, sin desplazamiento horizontal, y con la columna Fuente a la vista
	const tablas = page.locator('section.seccion .tabla-apilada');
	expect(await tablas.count()).toBeGreaterThan(0);
	for (const t of await tablas.all()) {
		const { ancho, visible } = await t.evaluate((el) => ({ ancho: el.scrollWidth - el.clientWidth, visible: el.offsetParent !== null }));
		if (visible) expect(ancho).toBeLessThanOrEqual(1);
	}
	await expect(page.locator('section.seccion .tabla-apilada td[data-etiqueta="Fuente"]').first()).toBeVisible();
	// barra de secciones sin scrollbar visible
	const barra = await page.locator('nav.indice ul').evaluate((ul) => getComputedStyle(ul).scrollbarWidth);
	expect(barra).toBe('none');
});

// ---------------------------------------------------------------- M12.2a (#249): la lista del mapa por familia
type IndLista = { codigo: string; tema: string; grupo?: string; mapa?: boolean; familia?: string; nombre_corto?: string; nombre: string };
const lista = indicadores as unknown as IndLista[];
const temasConGrupos = [...new Set(lista.filter((i) => i.mapa !== false).map((i) => `${i.tema}|${i.grupo ?? ''}`))];

/** Elige un tema (y su nivel educativo, si tiene) en el panel del mapa. */
async function elegirTemaGrupo(page: import('@playwright/test').Page, tema: string, grupo: string) {
	await page.getByRole('group', { name: 'Tema' }).getByText(tema, { exact: true }).click();
	if (grupo) await page.getByRole('group', { name: 'Nivel educativo' }).getByText(grupo, { exact: true }).click();
	await esperarQuieta(page);
}

test('AC-V36: la lista nunca ofrece un indicador «sin datos en el mapa», en ningún tema ni nivel educativo', async ({ page }, info) => {
	test.skip(vista(info.project.name) !== '1440', 'se recorre una vez, a 1440');
	await page.goto('');
	for (const tg of temasConGrupos) {
		const [tema, grupo] = tg.split('|');
		await elegirTemaGrupo(page, tema, grupo);
		await expect(page.getByText('sin datos en el mapa')).toHaveCount(0);
	}
});

test('AC-V37: un ítem por familia, con su nombre corto; con Educación → Primaria la lista entra sin scroll a 1440×900', async ({ page }, info) => {
	test.skip(vista(info.project.name) !== '1440', 'el criterio es a 1440×900');
	test.skip(!lista.some((i) => i.grupo === 'Primaria' && i.mapa !== false), 'estos datos no traen educación');
	await page.goto('');
	await elegirTemaGrupo(page, 'Educación', 'Primaria');
	const familias = lista.filter((i) => i.grupo === 'Primaria' && i.mapa !== false && (i.familia ?? i.codigo) === i.codigo);
	const items = page.locator('.lista-indicadores label.indicador');
	await expect(items).toHaveCount(familias.length);
	for (const f of familias) await expect(items.filter({ hasText: f.nombre_corto ?? f.nombre })).toHaveCount(1);
	// la lista entera (y el aviso de AC-V41, si está) se ve sin hacer scroll en el panel; nivel y período pueden quedar abajo
	const panel = page.locator('aside.opciones');
	const fondo = await panel.evaluate((p) => p.getBoundingClientRect().top + p.clientHeight);
	const ultimo = page.locator('.lista-indicadores label.indicador, p.info.fuera-del-mapa').last();
	expect((await ultimo.boundingBox())!.y + (await ultimo.boundingBox())!.height).toBeLessThanOrEqual(fondo + 1);
	expect(await panel.evaluate((p) => p.scrollTop)).toBe(0);
	for (const item of await items.all()) {
		const lineas = (sel: string) => item.locator(sel).evaluate((e) => Math.round(e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight)));
		expect(await lineas('.nombre')).toBeLessThanOrEqual(2);
		expect(await lineas('.detalle')).toBe(1);
	}
});

test('AC-V41: si un tema o nivel tiene indicadores fuera del mapa, un aviso lo dice y lleva al catálogo o a la ficha de Uruguay', async ({ page }, info) => {
	test.skip(vista(info.project.name) !== '1440', 'se prueba una vez, a 1440');
	const fuera = new Set(lista.filter((i) => i.mapa === false).map((i) => `${i.tema}|${i.grupo ?? ''}`));
	const casos = temasConGrupos.filter((tg) => fuera.has(tg));
	test.skip(!casos.length, 'en estos datos todo va al mapa');
	await page.goto('');
	for (const tg of casos) {
		const [tema, grupo] = tg.split('|');
		await elegirTemaGrupo(page, tema, grupo);
		const aviso = page.locator('p.info.fuera-del-mapa');
		await expect(aviso).toHaveCount(1);
		await expect(aviso.getByRole('link')).toHaveAttribute('href', tema === 'Educación' ? /\/educacion$/ : /\/territorio\/pais\/UY$/);
		// una oración, sin listar los indicadores ocultos
		const texto = (await aviso.textContent()) ?? '';
		expect(texto.split('.').filter((x) => x.trim()).length, texto).toBe(1);
		for (const i of lista.filter((x) => x.mapa === false && `${x.tema}|${x.grupo ?? ''}` === tg).slice(0, 50))
			expect(texto).not.toContain(i.nombre);
	}
	// un tema sin indicadores fuera del mapa no muestra el aviso
	const sinFuera = temasConGrupos.find((tg) => !fuera.has(tg));
	if (sinFuera) {
		await elegirTemaGrupo(page, ...(sinFuera.split('|') as [string, string]));
		await expect(page.locator('p.info.fuera-del-mapa')).toHaveCount(0);
	}
});

test('AC-V42: en celular el desplegable tiene los mismos ítems: uno por familia, con su nombre corto', async ({ page }, info) => {
	test.skip(vista(info.project.name) !== '390', 'el desplegable es el control de celular');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
	await abrirOpciones(page);
	for (const tg of temasConGrupos) {
		const [tema, grupo] = tg.split('|');
		await elegirTemaGrupo(page, tema, grupo);
		const familias = lista.filter((i) => `${i.tema}|${i.grupo ?? ''}` === tg && i.mapa !== false && (i.familia ?? i.codigo) === i.codigo);
		expect(await page.locator('#indicador-movil option').allTextContents(), tg).toEqual(familias.map((f) => f.nombre_corto ?? f.nombre));
	}
});

test('#249: una apertura abierta por URL marca su familia en la lista, y la lista o el desplegable vuelven al total', async ({ page }, info) => {
	const ap = lista.find((i) => i.mapa !== false && i.familia && i.familia !== i.codigo);
	test.skip(!ap, 'estos datos no traen aperturas en el mapa');
	await page.goto(`?indicador=${ap!.codigo}&nivel=departamento`);
	await esperarQuieta(page);
	const total = lista.find((i) => i.codigo === ap!.familia)!;
	if (vista(info.project.name) === '390' || vista(info.project.name) === '768') {
		await abrirOpciones(page);
		const sel = page.locator('#indicador-movil');
		await expect(sel).toHaveValue(ap!.codigo);
		await sel.selectOption(total.codigo);
	} else {
		const item = page.locator('.lista-indicadores label.indicador', { hasText: total.nombre_corto ?? total.nombre });
		await expect(item).toHaveClass(/activo/);
		await item.click();
	}
	await expect(page).toHaveURL(new RegExp(`indicador=${total.codigo}(&|$)`));
});
