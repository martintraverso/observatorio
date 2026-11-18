// F2.8b (#66): tema «Trabajo» en el mapa (AC-L23, AC-L24).
// La ECH sigue «en preparación»: estos tests corren sobre la vista previa (web.py --incluir-en-preparacion,
// ver app/README.md) y se saltean si el build no trae indicadores de Trabajo (como en CI).
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

const indicadores = JSON.parse(readFileSync('build/datos-web/indicadores.json', 'utf-8')) as {
	codigo: string;
	tema: string;
	niveles: string[];
	periodos: string[];
}[];
const trabajo = indicadores.filter((i) => i.tema === 'Trabajo');
const ultimo = trabajo[0]?.periodos.at(-1) ?? '';

test.skip(trabajo.length === 0, 'el build no trae datos de Trabajo (la ECH está «en preparación»)');

const leyenda = (page: Page) => page.getByRole('region', { name: 'Leyenda' }).locator('visible=true');
const panel = (page: Page) => page.getByRole('complementary', { name: 'Territorio seleccionado' });

test('AC-L23: el tema Trabajo ofrece los 7 indicadores por departamento y municipio de Montevideo', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'la lista de indicadores se prueba en escritorio');
	expect(trabajo).toHaveLength(7);
	for (const i of trabajo) expect(i.niveles).toEqual(expect.arrayContaining(['departamento', 'municipio_mvd']));
	await page.goto('');
	await page.getByRole('group', { name: 'Tema' }).getByRole('radio', { name: 'Trabajo' }).check();
	const lista = page.getByRole('group', { name: 'Indicador' }).getByRole('radio');
	await expect(lista).toHaveCount(7);
	const nivel = page.getByRole('group', { name: 'Nivel territorial' });
	await nivel.getByRole('radio', { name: 'Municipio (Montevideo)' }).check();
	await expect(page.getByText('no se publica por')).toHaveCount(0); // sin aviso de AC-M2: hay datos por municipio
	// la capa de municipios se ve y tiene polígonos pintados con clase
	await page.locator('section[aria-label="Mapa interactivo"]').scrollIntoViewIfNeeded();
	await page.waitForFunction(() => {
		type M = {
			loaded(): boolean;
			getLayoutProperty(l: string, p: string): string;
			queryRenderedFeatures(o: { layers: string[] }): { state: { clase?: number } }[];
		};
		const m = (window as unknown as { __mapa?: M }).__mapa;
		if (!m || !m.loaded() || m.getLayoutProperty('relleno-municipio_mvd', 'visibility') !== 'visible') return false;
		const f = m.queryRenderedFeatures({ layers: ['relleno-municipio_mvd'] });
		return f.length > 0 && f.every((x) => typeof x.state.clase === 'number');
	}, undefined, { timeout: 20_000 });
	await nivel.getByRole('radio', { name: 'Sección' }).check();
	const aviso = page.getByRole('status').filter({ hasText: 'no se publica por' });
	await expect(aviso).toContainText('no se publica por sección');
	await expect(aviso).toContainText('El nivel más detallado con datos es municipio (Montevideo)');
	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test('AC-L24: la leyenda y el panel nombran el trimestre móvil y la fuente', async ({ page }) => {
	const [inicio, fin] = ultimo.split('/');
	const meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'set', 'oct', 'nov', 'dic'];
	const etiqueta = `Trimestre móvil ${meses[Number(inicio.slice(5)) - 1]}–${meses[Number(fin.slice(5)) - 1]} ${fin.slice(0, 4)}`;
	await page.goto(`?indicador=tasa_actividad&nivel=departamento&periodo=${ultimo}&territorio=departamento/10`);
	await expect(leyenda(page)).toContainText('Tasa de actividad');
	await expect(leyenda(page)).toContainText(`Fuente: INE, ECH · ${etiqueta}`);
	await expect(leyenda(page)).toContainText(/\d+,\d a \d+,\d/); // clases con decimales
	await expect(panel(page)).toContainText(`Tasa de actividad · ${etiqueta}`);
	await expect(panel(page)).toContainText('Fuente: INE, ECH');
	await expect(panel(page)).toContainText('el INE lo publica para este período'); // total del país del INE
	await expect(page.getByRole('combobox', { name: 'Período' })).toHaveValue(ultimo);
	await expect(page.getByRole('combobox', { name: 'Período' }).locator('option:checked')).toHaveText(etiqueta);
});

test('AC-M3 con municipios: el municipio seleccionado se resalta y su panel se abre', async ({ page }) => {
	await page.goto(`?indicador=tasa_desempleo&nivel=municipio_mvd&periodo=${ultimo}&territorio=municipio_mvd/C`);
	await expect(panel(page)).toContainText('Municipio C');
	await page.locator('section[aria-label="Mapa interactivo"]').scrollIntoViewIfNeeded();
	const activar = page.getByRole('button', { name: 'Ver el mapa interactivo' });
	if (await activar.isVisible()) await activar.click();
	await page.waitForFunction(() => {
		type M = { loaded(): boolean; getFilter(l: string): unknown };
		const m = (window as unknown as { __mapa?: M }).__mapa;
		return !!m && m.loaded() && JSON.stringify(m.getFilter('seleccion-municipio_mvd')).includes('INE-2023/municipio_mvd/C');
	}, undefined, { timeout: 20_000 });
});

test('la nota del total del país depende del período (nunca se suma)', async ({ page }) => {
	const primero = trabajo[0].periodos[0]; // 2021-12/2022-02: el INE no publicó total del país
	await page.goto(`?indicador=tasa_actividad&nivel=departamento&periodo=${primero}&territorio=departamento/10`);
	await expect(panel(page)).toContainText('el INE no lo publicó para este período');
	await page.goto(`?indicador=tasa_actividad&nivel=departamento&periodo=${ultimo}&territorio=departamento/10`);
	await expect(panel(page)).toContainText('el INE lo publica para este período');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/10');
	await expect(panel(page)).toContainText('esta fuente no publica un total nacional');
});
