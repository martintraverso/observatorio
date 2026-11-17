import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

// Territorios reales del build: sirve igual con el fixture que con los datos completos.
const indice = JSON.parse(readFileSync('build/datos-web/territorios_index.json', 'utf-8')) as {
	nivel: string;
	codigo: string;
	nombre: string;
	depto: string;
}[];
const de = (nivel: string, depto = '07') => indice.find((t) => t.nivel === nivel && t.depto === depto)!;

const campo = (page: Page) => page.getByRole('combobox', { name: /Buscar departamento/ });
const lista = (page: Page) => page.getByRole('listbox', { name: 'Territorios encontrados' });

test.beforeEach(async ({ page }) => {
	await page.goto('fichas');
});

test('AC-S1: con 2 caracteres sugiere, sin importar tildes ni mayúsculas', async ({ page }) => {
	await campo(page).fill('s');
	await expect(lista(page)).toBeHidden();
	for (const consulta of ['san jose', 'SAN JOSÉ', 'San José']) {
		await campo(page).fill(consulta);
		await expect(lista(page).getByRole('option').first()).toContainText('San José');
		await expect(campo(page)).toHaveAttribute('aria-expanded', 'true');
	}
});

test('AC-S1: encuentra barrios de Montevideo', async ({ page }) => {
	const barrio = indice.find((t) => t.nivel === 'barrio_mvd')!;
	await campo(page).fill(barrio.nombre.slice(0, 5).toLowerCase());
	await expect(lista(page)).toContainText(barrio.nombre);
});

test('AC-S2: un código INE + Enter va al territorio', async ({ page }) => {
	for (const t of [de('departamento'), de('seccion'), de('localidad'), de('segmento')]) {
		await page.goto('fichas');
		await campo(page).fill(t.codigo);
		await campo(page).press('Enter');
		await expect(page).toHaveURL(new RegExp(`/territorio/${t.nivel}/${t.codigo}$`));
		await expect(page.getByRole('heading', { level: 1 })).toHaveText(t.nombre);
	}
});

test('AC-S3: los resultados muestran nivel y padre', async ({ page }) => {
	const seccion = de('seccion');
	await campo(page).fill(seccion.codigo);
	await expect(lista(page).getByRole('option').first()).toContainText(`Sección censal · Flores · ${seccion.codigo}`);
	const segmento = de('segmento');
	await campo(page).fill(segmento.codigo);
	await expect(lista(page).getByRole('option').first()).toContainText(
		new RegExp(`Segmento censal · Sección \\d+ · Flores · ${segmento.codigo}`)
	);
});

test('teclado: flechas, Enter y Escape (combobox ARIA)', async ({ page }) => {
	await campo(page).fill('07');
	const opciones = lista(page).getByRole('option');
	await expect(opciones.first()).toBeVisible();
	await campo(page).press('ArrowDown');
	await expect(opciones.first()).toHaveAttribute('aria-selected', 'true');
	await expect(campo(page)).toHaveAttribute('aria-activedescendant', 'buscar-sugerencias-0');
	await campo(page).press('ArrowDown');
	await expect(opciones.nth(1)).toHaveAttribute('aria-selected', 'true');
	await campo(page).press('ArrowUp');
	await expect(opciones.first()).toHaveAttribute('aria-selected', 'true');

	await campo(page).press('Escape');
	await expect(lista(page)).toBeHidden();
	await expect(campo(page)).toHaveValue('07');
	await campo(page).press('Escape');
	await expect(campo(page)).toHaveValue('');

	await campo(page).fill('07');
	await campo(page).press('ArrowDown');
	await campo(page).press('Enter');
	await expect(page).toHaveURL(/\/territorio\/departamento\/07$/);
	await expect(campo(page)).toHaveValue('');
});

test('clic en una sugerencia abre la ficha', async ({ page }) => {
	await campo(page).fill('flores');
	await lista(page).getByRole('option', { name: /^Flores/ }).first().click();
	await expect(page).toHaveURL(/\/territorio\/departamento\/07$/);
});

test('sin resultados lo dice', async ({ page }) => {
	await campo(page).fill('zzzz');
	await expect(page.getByText('Sin resultados para «zzzz».').first()).toBeVisible();
});

test('el índice se carga recién al usar el buscador (AC-G6)', async ({ page }) => {
	const pedidos: string[] = [];
	page.on('request', (r) => pedidos.push(r.url()));
	await page.goto('');
	await page.waitForLoadState('networkidle');
	expect(pedidos.some((u) => u.endsWith('territorios_index.json'))).toBe(false);
	await campo(page).fill('fl');
	await expect(lista(page)).toBeVisible();
	expect(pedidos.some((u) => u.endsWith('territorios_index.json'))).toBe(true);
});

test('accesibilidad con la lista abierta (axe)', async ({ page }) => {
	await campo(page).fill('san');
	await expect(lista(page)).toBeVisible();
	await campo(page).press('ArrowDown');
	const { violations } = await new AxeBuilder({ page }).analyze();
	const graves = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
	expect(graves.map((v) => `${v.id}: ${v.nodes.length} nodos`)).toEqual([]);
});

test('AC-S1: "paysandu" encuentra "Paysandú" (datos completos)', async ({ page }) => {
	test.skip(!indice.some((t) => t.nivel === 'departamento' && t.codigo === '11'), 'Paysandú no está en el fixture');
	await campo(page).fill('paysandu');
	await expect(lista(page).getByRole('option').first()).toContainText('Paysandú');
});
