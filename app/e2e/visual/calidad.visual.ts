// M10.0 (#78): controles de calidad visual sobre el sitio construido, en las cuatro vistas
// (proyectos `visual-*` de playwright.config.ts). Criterios: docs/ACCEPTANCE_CRITERIA_UI.md.
//
// Los problemas que el `main` todavía tiene están marcados con `pendiente(...)`: el test se
// espera que falle (test.fail) y se pone rojo cuando el problema se corrige, para que la
// historia que lo corrige saque la marca. Así el arnés prueba que detecta cada problema.
import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { nivelesConDatos } from '../../src/lib/mapa/estado.ts';
import { detectarDesbordes, esperarQuieta, revisarSegmentado, sinTextoInterno } from './ayudas';

type Territorio = { nivel: string; codigo: string; nombre: string; depto: string };
const indice = JSON.parse(readFileSync('build/datos-web/territorios_index.json', 'utf-8')) as Territorio[];
const fuentes = JSON.parse(readFileSync('build/datos-web/fuentes.json', 'utf-8')) as { id: string }[];
const indicadores = JSON.parse(readFileSync('build/datos-web/indicadores.json', 'utf-8')) as Parameters<typeof nivelesConDatos>[0];
const NIVELES = nivelesConDatos(indicadores);

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

for (const cantidad of [3, 4, 5]) {
	test(`AC-V1: el selector «Nivel territorial» con ${cantidad} niveles: una fila o una lista vertical, sin cortes`, async ({ page }) => {
		await page.goto('');
		await expect(page.locator(NIVEL_TERRITORIAL).getByRole('radio')).toHaveCount(NIVELES.length);
		// Con otra cantidad de niveles que la del build: se copian o se quitan opciones (el diseño no depende de cuántas haya).
		await page.locator(NIVEL_TERRITORIAL).evaluate((g, n) => {
			const opciones = [...g.querySelectorAll('label')];
			opciones.slice(n).forEach((o) => o.remove());
			for (let i = opciones.length; i < n; i++) {
				const copia = opciones[1].cloneNode(true) as HTMLElement;
				copia.querySelector('input')!.name = 'nivel-de-prueba';
				opciones[0].parentElement!.append(copia);
			}
		}, cantidad);
		await expect(page.locator(NIVEL_TERRITORIAL).locator('label')).toHaveCount(cantidad);
		expect(await revisarSegmentado(page, NIVEL_TERRITORIAL)).toEqual([]);
		expect(await detectarDesbordes(page)).toEqual([]);
	});
}

test('AC-V2: el municipio dice «Municipio» con la ayuda «Solo Montevideo»', async ({ page }) => {
	test.skip(!NIVELES.includes('municipio_mvd'), 'el build no trae datos por municipio (fixture)');
	await page.goto('');
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

	// `cambia`: el clic tiene que cambiar el estado en la URL (si no, el paso no probaría nada).
	const clics = [
		{ control: panel.getByRole('group', { name: 'Tema' }).getByText('Trabajo', { exact: true }), cambia: false },
		{ control: panel.getByRole('group', { name: 'Tema' }).getByText('Población', { exact: true }), cambia: false },
		{ control: panel.getByRole('group', { name: 'Indicador' }).locator('label.indicador:not(.activo)').first(), cambia: true },
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
	// Cada indicador por departamento, entrando por URL y esperando su propia leyenda.
	for (const i of indicadores.filter((x) => x.niveles.includes('departamento')) as unknown as { codigo: string; nombre: string }[]) {
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
