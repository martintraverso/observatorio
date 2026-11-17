import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

const leer = <T>(archivo: string): T => JSON.parse(readFileSync(`build/datos-web/${archivo}`, 'utf-8')) as T;
type Fuente = { id: string; nombre: string; organismo: string; temas: string[]; frecuencia: string; estado: string; licencia: string; contacto: string };
const fuentes = leer<Fuente[]>('fuentes.json');
const historial = leer<{ historial: { fuente_id: string; resultado: string }[] }>('capturas.json').historial;
const descargas = leer<{ archivos: { nombre: string; grupo: string }[] }>('descargas.json');
// La fuente del Censo (activa, con capturas e indicadores); hay otras en preparación.
const F = fuentes.find((f) => f.id === 'ine_unidades_geoestadisticas_2023')!;

test('AC-SRC1: /fuentes lista cada fuente con organismo, temas, nivel, frecuencia, captura y estado', async ({ page }) => {
	await page.goto('fuentes/');
	const filas = page.getByRole('table', { name: 'Fuentes de datos' }).locator('tbody tr');
	await expect(filas).toHaveCount(fuentes.length);
	const fila = filas.filter({ hasText: F.nombre });
	await expect(fila).toContainText(F.organismo);
	await expect(fila).toContainText(F.temas.join(', '));
	await expect(fila).toContainText('Segmento censal');
	await expect(fila).toContainText(F.frecuencia);
	await expect(fila).toContainText(/\d\d\/\d\d\/\d{4}/);
	await expect(fila).toContainText(F.estado);
	await expect(page.locator('.resumen')).toContainText('Activas');
});

test('los niveles se muestran con su nombre, nunca con el código interno', async ({ page }) => {
	await page.goto('fuentes/');
	await expect(page.getByRole('table', { name: 'Fuentes de datos' })).not.toContainText(/municipio_mvd|area_especial|barrio_mvd/);
	await expect(page.getByLabel('Nivel').locator('option')).not.toContainText([/_/]);
});

test('AC-SRC2: los filtros funcionan y se combinan', async ({ page }) => {
	await page.goto('fuentes/');
	const filas = page.getByRole('table', { name: 'Fuentes de datos' }).locator('tbody tr');
	await page.getByLabel('Estado').selectOption('a relevar');
	await expect(filas).toHaveCount(1);
	await expect(filas).toContainText('Ninguna fuente cumple estos filtros.');
	await page.getByRole('button', { name: 'Limpiar filtros' }).click();
	await expect(filas).toHaveCount(fuentes.length);
	await page.getByLabel('Organismo').selectOption(F.organismo);
	await page.getByLabel('Nivel').selectOption('segmento');
	await page.getByLabel('Estado').selectOption('activa');
	await expect(filas.filter({ hasText: F.nombre })).toHaveCount(1);
	await page.getByRole('searchbox', { name: 'Buscar', exact: true }).fill('no existe ninguna');
	await expect(filas).toContainText('Ninguna fuente cumple estos filtros.');
});

test('AC-SRC3 y AC-SRC4: detalle de la fuente con ficha técnica, indicadores, capturas y licencia literal', async ({ page }) => {
	await page.goto('fuentes/');
	await page.getByRole('link', { name: F.nombre }).click();
	await expect(page).toHaveURL(new RegExp(`/fuentes/${F.id}/?$`));
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(F.nombre);
	const tecnica = page.getByRole('region', { name: 'Ficha técnica' });
	await expect(tecnica.locator('dd.literal').first()).toHaveText(F.licencia); // exactamente como en los metadatos
	await expect(tecnica.locator('dd.literal').nth(1)).toHaveText(F.contacto);
	await expect(page.getByRole('table', { name: `Indicadores de ${F.nombre}` }).locator('tbody tr')).toHaveCount(4);
	const capturas = page.getByRole('table', { name: `Capturas de ${F.nombre}` }).locator('tbody tr');
	await expect(capturas).toHaveCount(historial.filter((c) => c.fuente_id === F.id).length);
	await expect(capturas.first()).toContainText(/\d\d\/\d\d\/\d{4}/);
	await expect(capturas.first()).toContainText('.zip');
	await expect(capturas.first()).toContainText(/Nuevo|Reprocesado|Sin cambios|Error/);
	await expect(page.getByRole('region', { name: 'Hasta dónde llega en el territorio' })).toContainText('Segmento censal');
	await expect(page.getByRole('link', { name: 'reportalo en GitHub' })).toHaveAttribute('href', /\/issues\/new\?/);
});

test('AC-D1 y AC-D2: /datos ofrece observaciones, territorios por nivel y la base, con tamaño, fecha y licencia', async ({ page }) => {
	await page.goto('datos');
	const nombres = descargas.archivos.map((a) => a.nombre);
	for (const n of ['observaciones.parquet', 'observaciones.csv', 'observatorio.duckdb', 'territorios_departamento.geojson', 'territorios_segmento.parquet']) {
		expect(nombres).toContain(n);
		const enlace = page.getByRole('link', { name: n, exact: true });
		await expect(enlace).toHaveAttribute('href', new RegExp(`/releases/latest/download/${n.replace('.', '\\.')}$`));
		const fila = page.getByRole('row').filter({ has: enlace });
		await expect(fila).toContainText(/\d+(,\d)? (B|kB|MB)/);
		await expect(fila).toContainText(/\d\d\/\d\d\/\d{4}/);
	}
	await expect(page.getByRole('link', { name: /\.(parquet|csv|geojson|duckdb|md)$/ })).toHaveCount(descargas.archivos.length);
	await expect(page.locator('.licencia')).toContainText('El uso es libre, citando como fuente al INE.');
	await expect(page.locator('.licencia')).toContainText('Cita sugerida: Observatorio Uruguay');
});

test('accesibilidad del detalle de fuente (axe)', async ({ page }) => {
	await page.goto(`fuentes/${F.id}/`);
	const { violations } = await new AxeBuilder({ page }).analyze();
	const graves = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
	expect(graves.map((v) => `${v.id}: ${v.nodes.length} nodos`)).toEqual([]);
});
