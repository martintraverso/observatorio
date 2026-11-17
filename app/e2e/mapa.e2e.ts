import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

const indice = JSON.parse(readFileSync('build/datos-web/territorios_index.json', 'utf-8')) as {
	nivel: string;
	codigo: string;
	nombre: string;
	bbox: [number, number, number, number];
}[];
const FLORES = indice.find((t) => t.nivel === 'departamento' && t.codigo === '07')!;

type MapaQuery = {
	getCanvas(): HTMLCanvasElement;
	project(p: [number, number]): { x: number; y: number };
	queryRenderedFeatures(p: [number, number]): { properties: { id?: string } }[];
};
type MapaVentana = { __mapa?: { loaded(): boolean; areTilesLoaded(): boolean; project(p: [number, number]): { x: number; y: number } } };

async function mapaListo(page: Page) {
	await page.waitForFunction(() => {
		const m = (window as unknown as MapaVentana).__mapa;
		return !!m && m.loaded() && m.areTilesLoaded();
	}, undefined, { timeout: 20_000 });
}

const leyenda = (page: Page) => page.getByRole('region', { name: 'Leyenda' });
const panel = (page: Page) => page.getByRole('complementary', { name: 'Territorio seleccionado' });

test('AC-M1 y AC-G7: coropleta con leyenda, unidades, fuente y atribución del INE', async ({ page }) => {
	await page.goto('');
	await mapaListo(page);
	await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible();
	await expect(leyenda(page)).toContainText('Personas');
	await expect(leyenda(page)).toContainText('(personas)');
	await expect(leyenda(page)).toContainText('Sin dato');
	await expect(leyenda(page)).toContainText('Fuente: INE');
	await expect(leyenda(page)).toContainText('2023');
	await expect(leyenda(page).getByRole('listitem')).not.toHaveCount(1); // hay clases además de "Sin dato"
	await expect(page.locator('.maplibregl-ctrl-attrib')).toContainText('Límites: INE, unidades geoestadísticas 2023');
});

test('AC-M5: el estado del mapa queda en la URL y se restaura', async ({ page }) => {
	await page.goto('');
	await mapaListo(page);
	await page.getByText('Vivienda', { exact: true }).click();
	await page.getByText('Sección', { exact: true }).click();
	await expect(page).toHaveURL(/indicador=viviendas_total/);
	await expect(page).toHaveURL(/nivel=seccion/);
	await expect(leyenda(page)).toContainText('Viviendas');

	await page.reload();
	await mapaListo(page);
	await expect(page.getByRole('radio', { name: 'Sección', exact: true })).toBeChecked();
	await expect(page.getByRole('radio', { name: 'Vivienda', exact: true })).toBeChecked();
	await expect(leyenda(page)).toContainText('Viviendas');
});

test('AC-M3: tocar un territorio lo selecciona y muestra sus datos', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'el clic sobre el lienzo se prueba en escritorio');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
	await mapaListo(page);
	// Un punto de Flores que se vea (que no lo tape la leyenda ni otro control), como tocaría una persona.
	const punto = await page.evaluate((bbox) => {
		const m = (window as unknown as { __mapa: MapaQuery }).__mapa;
		const c = m.getCanvas().getBoundingClientRect();
		for (let i = 1; i < 10; i++) {
			for (let j = 1; j < 10; j++) {
				const p = m.project([bbox[0] + ((bbox[2] - bbox[0]) * i) / 10, bbox[1] + ((bbox[3] - bbox[1]) * j) / 10]);
				const enFlores = m.queryRenderedFeatures([p.x, p.y]).some((f) => f.properties.id === 'INE-2023/departamento/07');
				if (enFlores && document.elementFromPoint(c.x + p.x, c.y + p.y) === m.getCanvas()) return { x: c.x + p.x, y: c.y + p.y };
			}
		}
		return null;
	}, FLORES.bbox);
	expect(punto).not.toBeNull();
	await page.mouse.click(punto!.x, punto!.y);
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	await expect(page).toHaveURL(/territorio=departamento%2F07/);
	await expect(panel(page)).toContainText('Departamento · Código INE 07');
	await expect(panel(page)).toContainText('26.271');
	await expect(panel(page)).toContainText('Fuente: INE');
	await expect(panel(page)).toContainText('no publica un total nacional');
	await expect(panel(page).getByRole('link', { name: 'Ver ficha completa' })).toHaveAttribute(
		'href',
		/territorio\/departamento\/07$/
	);
});

test('AC-M4: mini-mapa de ubicación del territorio seleccionado', async ({ page }) => {
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	const mini = panel(page).getByRole('img', { name: 'Ubicación de Flores en Uruguay' });
	await expect(mini).toBeVisible();
	await expect(mini.locator('path[fill="#e07a1f"]')).toHaveCount(1);
});

test('AC-M4: los territorios chicos llevan un anillo en el mini-mapa', async ({ page }) => {
	const seccion = indice.find((t) => t.nivel === 'seccion' && t.codigo.startsWith('07'))!;
	await page.goto(`?indicador=pob_total&nivel=seccion&periodo=2023&territorio=seccion/${seccion.codigo}`);
	const mini = panel(page).getByRole('img', { name: `Ubicación de ${seccion.nombre} en Uruguay` });
	await expect(mini.locator('circle, rect')).toHaveCount(1);
});

test('descargar CSV del territorio (columnas de AC-F5)', async ({ page }) => {
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	const [descarga] = await Promise.all([
		page.waitForEvent('download'),
		panel(page).getByRole('button', { name: 'Descargar CSV' }).click()
	]);
	expect(descarga.suggestedFilename()).toBe('observatorio_departamento_07.csv');
	const texto = readFileSync((await descarga.path())!, 'utf-8').replace(/^﻿/, '');
	const [cabecera, ...filas] = texto.trim().split('\r\n');
	expect(cabecera).toBe('territorio_id,nivel,codigo,nombre,indicador,periodo,valor,unidad,es_estimado,fuente,archivo_origen,sha256');
	expect(filas).toHaveLength(4);
	expect(filas.find((f) => f.includes(',pob_total,'))).toContain(',26271,personas,false,');
});

test('segmentos: pide acercar el mapa', async ({ page }) => {
	await page.goto('?indicador=pob_total&nivel=segmento&periodo=2023');
	await expect(page.getByText('Acercá el mapa para ver los segmentos.')).toBeVisible();
});

test('tema sin fuentes lo dice', async ({ page }) => {
	await page.goto('');
	await page.getByText('Educación', { exact: true }).click();
	await expect(page.getByText('Todavía no hay fuentes cargadas para este tema.')).toBeVisible();
});

test('AC-M6: en móvil, temas en fila de chips y panel como hoja inferior', async ({ page }, info) => {
	test.skip(info.project.name !== 'movil', 'diseño móvil');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	const chips = page.locator('.chips');
	await expect(chips).toHaveCSS('flex-wrap', 'nowrap');
	await expect(page.getByRole('combobox', { name: 'Indicador' })).toBeVisible();
	await expect(panel(page)).toHaveCSS('position', 'fixed');
	const caja = await panel(page).boundingBox();
	const alto = page.viewportSize()!.height;
	expect(Math.round(caja!.y + caja!.height)).toBe(alto); // pegado abajo
	expect(caja!.height).toBeLessThan(alto * 0.5);
	await panel(page).getByRole('button', { name: /Cerrar/ }).click();
	await expect(panel(page)).toBeHidden();
});

test('accesibilidad del mapa con el panel abierto (axe)', async ({ page }) => {
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	const { violations } = await new AxeBuilder({ page }).analyze();
	const graves = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
	expect(graves.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(' ')}`)).toEqual([]);
});
