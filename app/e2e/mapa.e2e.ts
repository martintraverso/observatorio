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
	// El mapa arranca cuando se ve (en móvil queda debajo de las opciones).
	await page.locator('section[aria-label="Mapa interactivo"]').scrollIntoViewIfNeeded();
	const activar = page.getByRole('button', { name: 'Ver el mapa interactivo' });
	if (await activar.isVisible()) await activar.click(); // en móvil el mapa arranca al tocarlo
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

test('AC-G1: los controles del mapa están en español', async ({ page }) => {
	await page.goto('');
	await mapaListo(page);
	await expect(page.getByRole('button', { name: 'Acercar', exact: true })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Alejar', exact: true })).toBeVisible();
	// Ningún texto de MapLibre en inglés (aria-label o title) dentro del mapa.
	const ingles = await page.locator('.maplibregl-map').evaluate((m) =>
		[...m.querySelectorAll('[aria-label],[title]')]
			.flatMap((e) => [e.getAttribute('aria-label'), e.getAttribute('title')])
			.filter((t): t is string => !!t && /\b(zoom|toggle|map|close|enter|exit|find|location|reset|drag|use)\b/i.test(t))
	);
	expect(ingles).toEqual([]);
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

test('en móvil el mapa arranca al tocarlo; en escritorio, solo', async ({ page }, info) => {
	await page.goto('');
	const activar = page.getByRole('button', { name: 'Ver el mapa interactivo' });
	if (info.project.name === 'movil') {
		await expect(activar).toBeVisible();
		expect(await page.evaluate(() => !!(window as unknown as MapaVentana).__mapa)).toBe(false);
		await activar.click();
	} else {
		await expect(activar).toHaveCount(0);
	}
	await mapaListo(page);
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
	expect(cabecera).toBe('territorio_id,nivel,codigo,nombre,indicador,periodo,periodo_inicio,periodo_fin,tipo_periodo,valor,unidad,es_estimado,fuente,archivo_origen,sha256');
	const ficha = JSON.parse(readFileSync('build/datos-web/fichas/departamento/07.json', 'utf-8')) as { observaciones: unknown[] };
	expect(filas).toHaveLength(ficha.observaciones.length); // 4 del Censo (más la ECH en la vista previa)
	expect(filas.find((f) => f.includes(',pob_total,'))).toContain(',2023,2023-01-01,2023-01-01,censo,26271,personas,false,');
});

test('segmentos: pide acercar el mapa', async ({ page }) => {
	await page.goto('?indicador=pob_total&nivel=segmento&periodo=2023');
	await expect(page.getByText('Acercá el mapa para ver los segmentos, o elegí un departamento:')).toBeVisible();
	await expect(page.getByRole('combobox', { name: 'Elegí un departamento' })).toBeVisible();
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

test('el selector de nivel ofrece solo niveles con datos y un nivel sin valores no rompe la página', async ({ page }) => {
	const indicadores = JSON.parse(readFileSync('build/datos-web/indicadores.json', 'utf-8')) as { niveles: string[] }[];
	const conMunicipio = indicadores.some((i) => i.niveles.includes('municipio_mvd'));
	const errores: string[] = [];
	page.on('pageerror', (e) => errores.push(e.message));
	await page.goto('?indicador=pob_total&nivel=municipio_mvd&periodo=2023');
	const nivel = page.getByRole('group', { name: 'Nivel territorial' });
	await expect(nivel.getByRole('radio', { name: 'Municipio Solo Montevideo' })).toHaveCount(conMunicipio ? 1 : 0);
	// llegado por URL a un nivel sin datos de Personas: aviso de AC-M2 y ningún error
	await expect(page.getByRole('status').filter({ hasText: 'no se publica por municipio' })).toBeVisible();
	await page.waitForLoadState('networkidle');
	expect(errores).toEqual([]);
});

test('AC-V6: el área del mapa muestra que está cargando hasta el primer dibujo', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'en móvil el mapa arranca al tocarlo');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023', { waitUntil: 'domcontentloaded' });
	const cargando = page.locator('section[aria-label="Mapa interactivo"]').getByRole('status').filter({ hasText: 'Cargando el mapa…' });
	await expect(cargando).toBeVisible({ timeout: 300 });
	await mapaListo(page);
	await expect(cargando).toHaveCount(0);
});

type Camara = { __mapa: { getZoom(): number; getCenter(): { lng: number; lat: number }; isMoving(): boolean } };

/** Espera a que el mapa quede quieto con el centro dentro de bbox y zoom ≥ zoomMinimo. */
async function encuadrado(page: Page, bbox: [number, number, number, number], zoomMinimo: number) {
	await page.waitForFunction(
		([b, z]) => {
			const m = (window as unknown as Camara).__mapa;
			const c = m.getCenter();
			return !m.isMoving() && m.getZoom() >= z && c.lng >= b[0] && c.lng <= b[2] && c.lat >= b[1] && c.lat <= b[3];
		},
		[bbox, zoomMinimo] as const,
		{ timeout: 10_000 }
	);
}

const ZOOM_SEGMENTOS = 9; // src/lib/mapa/estado.ts

/** Lleva el mapa a la vista del país (para que el encuadre que sigue no sea el que ya había). */
async function alPais(page: Page): Promise<number> {
	return page.evaluate(() => {
		const m = (window as unknown as { __mapa: { jumpTo(o: { center: [number, number]; zoom: number }): void; getZoom(): number } }).__mapa;
		m.jumpTo({ center: [-55.8, -32.5], zoom: 6 });
		return m.getZoom();
	});
}

const nivelRadio = (page: Page, nombre: string) =>
	page.getByRole('group', { name: 'Nivel territorial' }).getByRole('radio', { name: nombre, exact: true });

test('AC-V7: al elegir «Municipio» el mapa se encuadra en Montevideo', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'el encuadre se prueba en escritorio');
	const indicadores = JSON.parse(readFileSync('build/datos-web/indicadores.json', 'utf-8')) as { niveles: string[] }[];
	test.skip(!indicadores.some((i) => i.niveles.includes('municipio_mvd')), 'el build no trae datos por municipio (fixture)');
	const mvd = indice.find((t) => t.nivel === 'departamento' && t.codigo === '01')!;
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
	await mapaListo(page);
	const zoomPais = await page.evaluate(() => (window as unknown as Camara).__mapa.getZoom());
	await nivelRadio(page, 'Municipio Solo Montevideo').check();
	await encuadrado(page, mvd.bbox, zoomPais + 2);
});

test('AC-V7: «Segmento» con un departamento elegido se encuadra en él, con los segmentos dibujados', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'el encuadre se prueba en escritorio');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	await mapaListo(page);
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	await alPais(page);
	await nivelRadio(page, 'Segmento').check();
	await encuadrado(page, FLORES.bbox, ZOOM_SEGMENTOS);
	await expect(page.getByText('Acercá el mapa para ver los segmentos')).toHaveCount(0);
	// segmentos dibujados (con su capa visible y polígonos en pantalla)
	await page.waitForFunction(() => {
		const m = (window as unknown as { __mapa: { areTilesLoaded(): boolean; queryRenderedFeatures(o: { layers: string[] }): unknown[] } }).__mapa;
		return m.areTilesLoaded() && m.queryRenderedFeatures({ layers: ['relleno-segmento'] }).length > 0;
	}, undefined, { timeout: 15_000 });
});

test('AC-V7: «Sección» con un departamento elegido se encuadra en él', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'el encuadre se prueba en escritorio');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	await mapaListo(page);
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	const zoomPais = await alPais(page);
	await nivelRadio(page, 'Sección').check();
	await encuadrado(page, FLORES.bbox, zoomPais + 1);
});

test('AC-V7: «Segmento» sin departamento elegido ofrece «Elegí un departamento»', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'el encuadre se prueba en escritorio');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
	await mapaListo(page);
	await nivelRadio(page, 'Segmento').check();
	const elegir = page.getByRole('combobox', { name: 'Elegí un departamento' });
	await expect(elegir).toBeVisible();
	await expect(elegir.getByRole('option')).toHaveCount(1 + indice.filter((t) => t.nivel === 'departamento').length);
	await elegir.selectOption('07');
	await encuadrado(page, FLORES.bbox, ZOOM_SEGMENTOS);
	await expect(elegir).toHaveCount(0); // con zoom suficiente el aviso se va
});

test('AC-V9: el aviso nombra el nivel elegido y ofrece, como botones, los niveles con datos del más fino al más grueso', async ({ page }) => {
	await page.goto('?indicador=pob_total&nivel=municipio_mvd&periodo=2023');
	const aviso = page.getByRole('status').filter({ hasText: 'no se publica por' });
	await expect(aviso).toContainText('«Personas» no se publica por municipio. Disponible por:');
	await expect(aviso.getByRole('button')).toHaveText(['segmento', 'sección', 'departamento']);
	await aviso.getByRole('button', { name: 'sección' }).click();
	await expect(nivelRadio(page, 'Sección')).toBeChecked();
	await expect(aviso).toHaveCount(0);
});

test('AC-V8: al ir a un nivel más fino el panel se vacía (no queda un territorio de otro nivel)', async ({ page }) => {
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	await nivelRadio(page, 'Segmento').check();
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveCount(0);
	await expect(page).not.toHaveURL(/territorio=/);
});

test('AC-V8: al ir a un nivel más grueso se elige el que contiene al territorio', async ({ page }) => {
	const seccion = indice.find((t) => t.nivel === 'seccion' && t.codigo.startsWith('07'))!;
	await page.goto(`?indicador=pob_total&nivel=seccion&periodo=2023&territorio=seccion/${seccion.codigo}`);
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(seccion.nombre);
	await nivelRadio(page, 'Departamento').check();
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	await expect(page).toHaveURL(/territorio=departamento%2F07/);
	// y si el territorio es del nivel elegido, se mantiene
	await nivelRadio(page, 'Departamento').check();
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
});
