import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

// Territorios reales del build (sirve igual con el fixture que con los datos completos).
const indice = JSON.parse(readFileSync('build/datos-web/territorios_index.json', 'utf-8')) as {
	nivel: string;
	codigo: string;
	nombre: string;
	depto: string;
}[];
const seccion = indice.find((t) => t.nivel === 'seccion' && t.depto === '07')!;
const segmento = indice.find((t) => t.nivel === 'segmento' && t.depto === '07')!;

// Rutas sin barra inicial: se resuelven contra baseURL (…/observatorio/).
const RUTAS = [
	{ ruta: '', titulo: 'Mapa' },
	{ ruta: 'fichas', titulo: 'Fichas' },
	{ ruta: 'datos', titulo: 'Datos' },
	{ ruta: 'fuentes', titulo: 'Fuentes' },
	{ ruta: 'territorio/departamento/07', titulo: 'Flores' }
];

async function sinErroresDeConsola(page: Page) {
	const errores: string[] = [];
	page.on('console', (m) => m.type() === 'error' && errores.push(m.text()));
	page.on('pageerror', (e) => errores.push(e.message));
	return errores;
}

for (const { ruta, titulo } of RUTAS) {
	test.describe(`/${ruta}`, () => {
		test('carga directa, título, navegación y sin errores', async ({ page }) => {
			const errores = await sinErroresDeConsola(page);
			const r = await page.goto(ruta);
			expect(r?.status()).toBe(200);
			await expect(page.getByRole('heading', { level: 1 })).toHaveText(titulo);
			await expect(page.getByRole('navigation', { name: 'Principal' })).toBeVisible();
			await expect(page.getByRole('searchbox', { name: /Buscar departamento/ })).toBeVisible();
			await expect(page.getByRole('contentinfo')).toContainText('Fuente: INE');
			await page.waitForLoadState('networkidle');
			expect(errores).toEqual([]);
		});

		test('accesibilidad: sin violaciones serias ni críticas (axe)', async ({ page }) => {
			await page.goto(ruta);
			const { violations } = await new AxeBuilder({ page }).analyze();
			const graves = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
			expect(graves.map((v) => `${v.id}: ${v.nodes.length} nodos`)).toEqual([]);
		});

		test('sin scroll horizontal de la página', async ({ page }) => {
			await page.goto(ruta);
			const desborde = await page.evaluate(
				() => document.documentElement.scrollWidth - document.documentElement.clientWidth
			);
			expect(desborde).toBeLessThanOrEqual(0);
		});
	});
}

test('AC-G3: las URL de sección y segmento abren directo (sitio estático)', async ({ page }) => {
	for (const t of [seccion, segmento]) {
		const r = await page.goto(`territorio/${t.nivel}/${t.codigo}`);
		expect(r?.status()).toBe(200);
		await expect(page.getByRole('heading', { level: 1 })).toHaveText(t.nombre);
		await expect(page.getByText(`Código INE ${t.codigo}`)).toBeVisible();
	}
});

test('AC-G3: un territorio inexistente da 404 en español', async ({ page }) => {
	const r = await page.goto('territorio/departamento/99');
	expect(r?.status()).toBe(404);
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Página no encontrada');
});

test('AC-G1 y AC-G2: valores en es-UY, con fuente y período', async ({ page }) => {
	await page.goto('territorio/departamento/07');
	const filas = page.getByRole('table', { name: 'Datos de Flores' }).locator('tbody tr');
	await expect(filas).toHaveCount(4);
	const personas = page.getByRole('row', { name: /^Personas / });
	await expect(personas).toContainText('26.271 personas');
	for (const fila of await filas.all()) {
		await expect(fila).toContainText('2023');
		await expect(fila).toContainText('Instituto Nacional de Estadística');
	}
});

test('navegar entre páginas sin recargar mantiene los datos', async ({ page }) => {
	await page.goto('fichas');
	await page.getByRole('link', { name: 'Flores' }).first().click();
	await expect(page).toHaveURL(/\/observatorio\/territorio\/departamento\/07$/);
	await page.getByRole('link', { name: seccion.nombre }).first().click();
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(seccion.nombre);
	await expect(page.getByRole('navigation', { name: 'Ubicación' })).toContainText('Flores');
});

test('teclado: el primer Tab lleva a "Saltar al contenido"', async ({ page }) => {
	await page.goto('');
	await page.keyboard.press('Tab');
	await expect(page.getByRole('link', { name: 'Saltar al contenido' })).toBeFocused();
});

test('áreas táctiles de al menos 44 px en la navegación', async ({ page }) => {
	await page.goto('');
	for (const link of await page.getByRole('navigation', { name: 'Principal' }).getByRole('link').all()) {
		const caja = await link.boundingBox();
		expect(caja!.height).toBeGreaterThanOrEqual(44);
	}
});

test('AC-G6: las páginas de listado pesan poco (no incrustan el índice ni el manifest)', async ({ request }) => {
	for (const ruta of ['', 'fichas', 'datos', 'fuentes']) {
		const cuerpo = await (await request.get(ruta)).body();
		expect(cuerpo.length, `/${ruta}`).toBeLessThan(150_000);
	}
});
