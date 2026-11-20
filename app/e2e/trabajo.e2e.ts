// F2.8b (#66): tema «Trabajo» en el mapa (AC-L23, AC-L24).
// La ECH sigue «en preparación»: estos tests corren sobre la vista previa (web.py --incluir-en-preparacion,
// ver app/README.md) y se saltean si el build no trae indicadores de Trabajo (como en CI).
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { abrirOpciones } from './visual/ayudas';

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
	await nivel.getByRole('radio', { name: 'Municipio Solo Montevideo' }).check();
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
	await expect(aviso).toContainText('Disponible por:');
	await expect(aviso.getByRole('button')).toHaveText(['municipio', 'departamento']);
	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test('AC-L24: la leyenda y el panel nombran el trimestre móvil y la fuente', async ({ page }, info) => {
	const [inicio, fin] = ultimo.split('/');
	const meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'set', 'oct', 'nov', 'dic'];
	const etiqueta = `Trimestre móvil ${meses[Number(inicio.slice(5)) - 1]}–${meses[Number(fin.slice(5)) - 1]} ${fin.slice(0, 4)}`;
	await page.goto(`?indicador=tasa_actividad&nivel=departamento&periodo=${ultimo}&territorio=departamento/10`);
	await expect(leyenda(page)).toContainText('Tasa de actividad');
	await expect(leyenda(page)).toContainText(`Fuente: INE, ECH · ${etiqueta}`);
	await expect(leyenda(page)).toContainText(/\d+,\d a \d+,\d/); // clases con decimales
	await expect(panel(page)).toContainText(`Tasa de actividad · ${etiqueta}`);
	await expect(panel(page)).toContainText('Fuente: INE, ECH');
	await expect(panel(page)).toContainText('Total del país: en la ficha de Uruguay.'); // total del país del INE
	// en celular el período también se lee en la barra compacta, y el selector está en la hoja (AC-V13)
	if (info.project.name === 'movil') await expect(page.getByRole('button', { name: /Cambiar$/ })).toContainText(etiqueta);
	await abrirOpciones(page);
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
	await expect(panel(page)).toContainText('Total del país: no publicado para este período');
	await page.goto(`?indicador=tasa_actividad&nivel=departamento&periodo=${ultimo}&territorio=departamento/10`);
	await expect(panel(page)).toContainText('Total del país: en la ficha de Uruguay.');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/10');
	await expect(panel(page)).toContainText('Total del país: no publicado por la fuente.');
});

// ---------------------------------------------------------------- F2.8c (#67): serie en las fichas (AC-L25)

const ficha = (nivel: string, codigo: string) =>
	JSON.parse(readFileSync(`build/datos-web/fichas/${nivel}/${codigo}.json`, 'utf-8')) as {
		observaciones: { indicador: string; periodo: string; tipo_periodo: string; valor: number | null }[];
	};
const nPeriodos = (nivel: string, codigo: string, indicador: string) =>
	ficha(nivel, codigo).observaciones.filter((o) => o.indicador === indicador && o.tipo_periodo !== 'censo' && o.valor !== null).length;

test('AC-L25: la ficha de un departamento muestra la serie desde 2022 frente al total del país', async ({ page }) => {
	await page.goto('territorio/departamento/10');
	const seccion = page.locator('#trabajo');
	const grafico = seccion.getByRole('img');
	await expect(grafico).toHaveAttribute('data-puntos', String(nPeriodos('departamento', '10', 'tasa_actividad')));
	await expect(grafico).toHaveAttribute('data-puntos-pais', String(nPeriodos('pais', 'UY', 'tasa_actividad')));
	expect(nPeriodos('departamento', '10', 'tasa_actividad')).toBeGreaterThan(nPeriodos('pais', 'UY', 'tasa_actividad'));
	await expect(grafico).toHaveAttribute('aria-label', /Tasa de actividad: \d+ períodos desde Trimestre móvil dic 2021–feb 2022/);
	await expect(seccion).toContainText('Total del país (INE, desde');
	const selector = seccion.getByRole('combobox', { name: 'Indicador' });
	await expect(selector.locator('option')).toHaveCount(7);
	await selector.selectOption({ label: 'Tasa de desempleo' });
	await expect(grafico).toHaveAttribute('aria-label', /^Tasa de desempleo:/);
	await expect(seccion.locator('details tbody tr')).toHaveCount(
		ficha('departamento', '10').observaciones.filter((o) => o.tipo_periodo !== 'censo').length
	);
	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test('AC-L25: municipios con serie y comparación; la ficha del país, sin línea de comparación', async ({ page }) => {
	await page.goto('territorio/municipio_mvd/CH');
	await expect(page.locator('#trabajo').getByRole('img')).toHaveAttribute('data-puntos', String(nPeriodos('municipio_mvd', 'CH', 'tasa_actividad')));
	await expect(page.locator('#trabajo').getByRole('img')).toHaveAttribute('data-puntos-pais', /^[1-9]\d*$/);
	await page.goto('territorio/pais/UY');
	await expect(page.locator('#trabajo').getByRole('img')).toHaveAttribute('data-puntos-pais', '0');
	await expect(page.locator('#trabajo')).not.toContainText('Total del país (INE');
});

// ---------------------------------------------------------------- F2.8d (#68): advertencias y sin rankings (AC-L26)

const TEMAS_ADVERTENCIAS = [/lugar de residencia/, /zafrales o estacionales/, /muestra/, /ranking/];

test('AC-L26: las advertencias del INE se ven junto a los datos de trabajo (ficha y panel)', async ({ page }) => {
	await page.goto('territorio/departamento/10');
	const enFicha = page.locator('#trabajo').getByRole('group').filter({ hasText: 'Advertencias del INE' });
	await expect(enFicha).toBeVisible();
	for (const t of TEMAS_ADVERTENCIAS) await expect(enFicha).toContainText(t);
	await expect(page.locator('#poblacion')).not.toContainText('Advertencias del INE'); // el Censo no las trae
	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

	await page.goto(`?indicador=tasa_desempleo&nivel=departamento&periodo=${ultimo}&territorio=departamento/10`);
	const enPanel = panel(page).getByRole('group').filter({ hasText: 'Advertencias del INE' });
	await expect(enPanel).toBeVisible();
	for (const t of TEMAS_ADVERTENCIAS) await expect(enPanel).toContainText(t);
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/10');
	await expect(panel(page)).toContainText('Maldonado');
	await expect(panel(page)).not.toContainText('Advertencias del INE');
});

test('AC-L26: ninguna vista ofrece un ranking de territorios por el valor de un período', async ({ page }) => {
	for (const ruta of ['', 'fichas', 'territorio/departamento/01', 'territorio/pais/UY']) {
		await page.goto(ruta);
		await expect(page.locator('[aria-sort], th button')).toHaveCount(0); // sin columnas ordenables
	}
	// los municipios de Montevideo se listan por código, no por valor
	await page.goto('territorio/departamento/01');
	await page.getByRole('tab', { name: /^Municipio \(Montevideo\)/ }).click();
	const nombres = await page.getByRole('tabpanel').locator('tbody tr th, tbody tr td:first-child').allTextContents();
	const letras = nombres.map((n) => n.trim().replace(/^Municipio /, '')).filter((n) => /^[A-Z]{1,2}$/.test(n));
	expect(letras).toEqual(['A', 'B', 'C', 'CH', 'D', 'E', 'F', 'G']);
});

test('AC-V20 y AC-V21: el gráfico de la serie tiene ejes redondos y legibles, decimales parejos y selector con estilo', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'las etiquetas del eje x se piden en escritorio');
	await page.goto('territorio/departamento/10');
	const seccion = page.locator('#trabajo');
	const grafico = seccion.getByRole('img');
	await expect(grafico).toBeVisible();
	// eje y: valores redondos con paso de 1, 2, 2,5 o 5 × 10ⁿ
	const y = await grafico.locator('text.eje[text-anchor="end"]').allTextContents();
	const marcas = y.map((t) => Number(t.replace(/\./g, '').replace(',', '.'))).filter((v) => !Number.isNaN(v));
	const paso = marcas[1] - marcas[0];
	expect(marcas.length).toBeGreaterThanOrEqual(3);
	const mantisa = Number((paso / 10 ** Math.floor(Math.log10(paso))).toFixed(6));
	expect([1, 2, 2.5, 5]).toContain(mantisa);
	for (let i = 1; i < marcas.length; i++) expect(Math.abs(marcas[i] - marcas[i - 1] - paso)).toBeLessThan(1e-6);
	// eje x: al menos 4 etiquetas
	expect(await grafico.locator('text.eje[y="232"]').count()).toBeGreaterThanOrEqual(4);
	// territorio y país con los mismos decimales
	const ultimo = (await seccion.locator('dl.ultimo dd').textContent()) ?? '';
	const numeros = [...ultimo.matchAll(/\d+(?:,(\d+))?/g)].map((m) => (m[1] ?? '').length);
	expect(new Set(numeros).size, ultimo).toBe(1);
	// selector con el estilo del resto
	const estilo = await seccion.getByRole('combobox', { name: 'Indicador' }).evaluate((el) => getComputedStyle(el).borderRadius);
	expect(estilo).not.toBe('0px');
	// AC-V21
	await expect(seccion.locator('figcaption')).toContainText(/Total del país \(INE, desde [a-z]{3} \d{4}–[a-z]{3} \d{4}\)/);
});
