// M10.0 (#78): los helpers detectan cada problema (y no dan falsos positivos), sobre HTML armado a mano.
// No dependen de los datos del build, así que prueban la detección también con el fixture de CI.
import { expect, test } from '@playwright/test';
import { detectarDesbordes, revisarSegmentado, sinTextoInterno } from './ayudas';

const BASE = '<style>body{font:16px/1.4 sans-serif;margin:0} .caja{width:120px}</style>';

test.describe('detectarDesbordes (AC-V5)', () => {
	test('acepta textos que entran en su caja', async ({ page }) => {
		await page.setContent(`${BASE}
			<button class="caja">Departamento</button>
			<a href="#">Un enlace</a>
			<table><tr><th>Fuente</th></tr></table>
			<div role="tab" class="caja">Mapa</div>
			<dl class="kpis"><dd>26.271</dd></dl>
			<div style="overflow-x:auto;width:100px"><a href="#" style="white-space:nowrap">un enlace largo que se desplaza</a></div>
			<span style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)"><a href="#">solo lectores</a></span>`);
		expect(await detectarDesbordes(page)).toEqual([]);
	});

	test('detecta texto que desborda su caja, con y sin puntos suspensivos', async ({ page }) => {
		await page.setContent(`${BASE}
			<button style="width:60px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">Departamento</button>
			<div role="tab" style="width:40px;white-space:nowrap">Pestaña larga</div>
			<dl class="kpis"><dd style="width:50px;white-space:nowrap">15.973 km²</dd></dl>`);
		const p = await detectarDesbordes(page);
		expect(p).toHaveLength(3);
		expect(p[0]).toContain('«Departamento»: el texto desborda a lo ancho');
		expect(p[1]).toContain('«Pestaña larga»');
		expect(p[2]).toContain('«15.973 km²»');
	});

	test('detecta texto que desborda a lo alto en una caja de alto fijo', async ({ page }) => {
		await page.setContent(`${BASE}<label style="display:block;width:150px;height:20px">Municipio (Montevideo)</label>`);
		expect(await detectarDesbordes(page)).toEqual([expect.stringContaining('desborda a lo alto')]);
	});

	test('detecta un enlace recortado por un contenedor con overflow hidden', async ({ page }) => {
		await page.setContent(`${BASE}<div style="width:80px;overflow:hidden;white-space:nowrap"><a href="#">un enlace bastante largo</a></div>`);
		expect(await detectarDesbordes(page)).toEqual([expect.stringContaining('queda recortado por div')]);
	});

	test('detecta una opción de segmentado en dos líneas (AC-V1)', async ({ page }) => {
		await page.setContent(`${BASE}
			<div class="segmentado" style="display:grid;grid-template-columns:repeat(3,150px)">
				<label><input type="radio" name="n">Sección</label>
				<label><input type="radio" name="n">Municipio (Montevideo)</label>
			</div>`);
		expect(await detectarDesbordes(page)).toEqual([expect.stringContaining('«Municipio (Montevideo)»: la opción ocupa 2 líneas')]);
	});
});

test.describe('revisarSegmentado (AC-V1)', () => {
	const grupo = (estilo: string, opciones: string[]) =>
		`${BASE}<fieldset id="g"><legend>Nivel territorial</legend><div style="${estilo}">${opciones
			.map((o) => `<label style="display:flex;min-height:40px;white-space:nowrap"><input type="radio" name="n">${o}</label>`)
			.join('')}</div></fieldset>`;

	test('acepta una fila o una lista vertical', async ({ page }) => {
		await page.setContent(grupo('display:flex', ['Departamento', 'Sección', 'Segmento']));
		expect(await revisarSegmentado(page, '#g')).toEqual([]);
		await page.setContent(grupo('display:flex;flex-direction:column', ['Departamento', 'Municipio', 'Sección', 'Segmento']));
		expect(await revisarSegmentado(page, '#g')).toEqual([]);
	});

	test('detecta una opción sola en la segunda fila (grilla de 3 con 4 opciones)', async ({ page }) => {
		await page.setContent(grupo('display:grid;grid-template-columns:repeat(3,1fr);width:300px', ['Departamento', 'Municipio', 'Sección', 'Segmento']));
		expect(await revisarSegmentado(page, '#g')).toEqual([expect.stringContaining('no están en una fila ni en una lista vertical')]);
	});

	test('detecta opciones de alturas distintas', async ({ page }) => {
		await page.setContent(`${BASE}<fieldset id="g"><div style="display:flex;align-items:flex-start">
			<label style="height:40px">Uno</label><label style="height:60px">Dos</label></div></fieldset>`);
		expect(await revisarSegmentado(page, '#g')).toEqual([expect.stringContaining('alturas distintas')]);
	});
});

test.describe('sinTextoInterno (AC-V19)', () => {
	test('acepta textos públicos', async ({ page }) => {
		await page.setContent(`${BASE}<p>Licencia: no publicada por el INE. Se cita la fuente. TODOS los departamentos.</p>
			<script>const x = 'Decisión del mantenedor';</script>`);
		expect(await sinTextoInterno(page)).toEqual([]);
	});

	test('detecta notas del mantenedor, también dentro de un bloque cerrado o en atributos', async ({ page }) => {
		await page.setContent(`${BASE}<details><summary>Licencia</summary>Decisión del mantenedor (2026-11-17): se deja asentado que…</details>
			<button title="TODO: revisar">Copiar</button><p>FIXME</p>`);
		const p = await sinTextoInterno(page);
		expect(p).toHaveLength(4);
		expect(p.join('\n')).toContain('Decisión del mantenedor');
	});
});
