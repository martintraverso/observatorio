import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { abrirOpciones } from './visual/ayudas';

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
	await abrirOpciones(page);
	await page.getByText('Vivienda', { exact: true }).click();
	await page.getByText('Sección', { exact: true }).click();
	await expect(page).toHaveURL(/indicador=viviendas_total/);
	await expect(page).toHaveURL(/nivel=seccion/);
	await expect(leyenda(page)).toContainText('Viviendas');

	await page.reload();
	await mapaListo(page);
	await abrirOpciones(page);
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
	await expect(panel(page)).toContainText('Total del país: no publicado por la fuente.');
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
	expect(cabecera).toBe('territorio_id,nivel,codigo,nombre,indicador,periodo,periodo_inicio,periodo_fin,tipo_periodo,valor,unidad,es_estimado,fuente,archivo_origen,sha256,cuadro,es_derivado');
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
	await abrirOpciones(page);
	await page.getByText('Educación', { exact: true }).click();
	await expect(page.getByText('Todavía no hay fuentes cargadas para este tema.')).toBeVisible();
});

test('AC-M6: en móvil, temas en fila de chips y panel como hoja inferior', async ({ page }, info) => {
	test.skip(info.project.name !== 'movil', 'diseño móvil');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	const chips = page.locator('.chips');
	await expect(chips).toHaveCSS('flex-wrap', 'nowrap');
	await abrirOpciones(page);
	await expect(page.getByRole('combobox', { name: 'Indicador' })).toBeVisible();
	await page.getByRole('button', { name: 'Listo' }).click();
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

test('el selector de nivel ofrece solo niveles con datos; AC-N8: un enlace a un nivel sin datos abre en uno que sí', async ({ page }) => {
	const indicadores = JSON.parse(readFileSync('build/datos-web/indicadores.json', 'utf-8')) as { niveles: string[] }[];
	const conMunicipio = indicadores.some((i) => i.niveles.includes('municipio_mvd'));
	const errores: string[] = [];
	page.on('pageerror', (e) => errores.push(e.message));
	// Personas no se publica por municipio: el enlace (viejo o escrito a mano) abre en Departamento, el nivel que lo
	// contiene (AC-N7), reescribe la URL y no muestra el aviso de AC-M2 (reemplaza el test del aviso por URL).
	await page.goto('?indicador=pob_total&nivel=municipio_mvd&periodo=2023');
	await expect(page).toHaveURL(/nivel=departamento/);
	await abrirOpciones(page);
	const nivel = page.getByRole('group', { name: 'Nivel territorial' });
	await expect(nivel.getByRole('radio', { name: 'Municipio Solo Montevideo' })).toHaveCount(conMunicipio ? 1 : 0);
	await expect(nivel.getByRole('radio', { name: 'Departamento' })).toBeChecked();
	await expect(page.getByText('no se publica por')).toHaveCount(0);
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
	await abrirOpciones(page);
	await nivelRadio(page, 'Municipio Solo Montevideo').check();
	await encuadrado(page, mvd.bbox, zoomPais + 2);
});

test('AC-V7: «Segmento» con un departamento elegido se encuadra en él, con los segmentos dibujados', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'el encuadre se prueba en escritorio');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	await mapaListo(page);
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	await alPais(page);
	await abrirOpciones(page);
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
	await abrirOpciones(page);
	await nivelRadio(page, 'Sección').check();
	await encuadrado(page, FLORES.bbox, zoomPais + 1);
});

test('AC-V7: «Segmento» sin departamento elegido ofrece «Elegí un departamento»', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'el encuadre se prueba en escritorio');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
	await mapaListo(page);
	await abrirOpciones(page);
	await nivelRadio(page, 'Segmento').check();
	const elegir = page.getByRole('combobox', { name: 'Elegí un departamento' });
	await expect(elegir).toBeVisible();
	await expect(elegir.getByRole('option')).toHaveCount(1 + indice.filter((t) => t.nivel === 'departamento').length);
	await elegir.selectOption('07');
	await encuadrado(page, FLORES.bbox, ZOOM_SEGMENTOS);
	await expect(elegir).toHaveCount(0); // con zoom suficiente el aviso se va
});

// AC-V9 (el aviso por URL a un nivel sin datos): desde M11.2 ese enlace abre en un nivel con datos (AC-N8, test de
// arriba). El texto y los botones del aviso los prueba estado.spec.ts; M11.4 lo saca del mapa (AC-N9).
test('AC-N8: un enlace a un nivel que el indicador ofrece se respeta (Barrio para Personas)', async ({ page }) => {
	const indicadores = JSON.parse(readFileSync('build/datos-web/indicadores.json', 'utf-8')) as { codigo: string; niveles: string[] }[];
	test.skip(!indicadores.find((i) => i.codigo === 'pob_total')?.niveles.includes('barrio_mvd'), 'sin datos por barrio');
	await page.goto('?indicador=pob_total&nivel=barrio_mvd&periodo=2023');
	await abrirOpciones(page);
	await expect(nivelRadio(page, 'Barrio Solo Montevideo')).toBeChecked();
	await expect(page).toHaveURL(/nivel=barrio_mvd/);
	await expect(page.getByText('no se publica por')).toHaveCount(0);
});

test('AC-V8: al ir a un nivel más fino el panel se vacía (no queda un territorio de otro nivel)', async ({ page }) => {
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	await abrirOpciones(page);
	await nivelRadio(page, 'Segmento').check();
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveCount(0);
	await expect(page).not.toHaveURL(/territorio=/);
});

test('AC-V8: al ir a un nivel más grueso se elige el que contiene al territorio', async ({ page }) => {
	const seccion = indice.find((t) => t.nivel === 'seccion' && t.codigo.startsWith('07'))!;
	await page.goto(`?indicador=pob_total&nivel=seccion&periodo=2023&territorio=seccion/${seccion.codigo}`);
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(seccion.nombre);
	await abrirOpciones(page);
	await nivelRadio(page, 'Departamento').check();
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	await expect(page).toHaveURL(/territorio=departamento%2F07/);
});

test('AC-V8: si el territorio es del nivel elegido, se mantiene', async ({ page }) => {
	await page.goto('?indicador=pob_total&nivel=seccion&periodo=2023&territorio=departamento/07');
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	await abrirOpciones(page);
	await nivelRadio(page, 'Departamento').check();
	await expect(page).toHaveURL(/nivel=departamento/);
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	await expect(page).toHaveURL(/territorio=departamento%2F07/);
});

test('AC-V8: si la ficha del territorio todavía no llegó, igual se elige el departamento que lo contiene', async ({ page }) => {
	const seccion = indice.find((t) => t.nivel === 'seccion' && t.codigo.startsWith('07'))!;
	// la ficha de la sección tarda: el cambio de nivel no puede usar la ficha de otro territorio
	await page.route(`**/fichas/seccion/${seccion.codigo}.json`, async (r) => {
		await new Promise((ok) => setTimeout(ok, 1500));
		await r.continue();
	});
	await page.goto(`?indicador=pob_total&nivel=seccion&periodo=2023&territorio=seccion/${seccion.codigo}`);
	await abrirOpciones(page);
	await nivelRadio(page, 'Departamento').check();
	await expect(page).toHaveURL(/territorio=departamento%2F07/);
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
});

test('AC-V10: sin territorio elegido el mapa ocupa al menos el 70 % del ancho', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'el panel lateral existe en escritorio');
	for (const width of [1440, 1024]) {
		await page.setViewportSize({ width, height: 900 });
		await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
		const proporcion = await page.evaluate(
			() => document.querySelector('section.centro')!.getBoundingClientRect().width / document.querySelector('.pantalla')!.getBoundingClientRect().width
		);
		expect(proporcion, `${width} px`).toBeGreaterThanOrEqual(0.7);
		await expect(panel(page)).toHaveCount(0);
		await expect(page.getByText('Tocá un territorio en el mapa para ver sus datos.')).toBeVisible();
	}
	// al elegir un territorio aparece el panel
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Flores');
	await expect(page.getByText('Tocá un territorio en el mapa para ver sus datos.')).toHaveCount(0);
});

test('AC-V12: un departamento que casi no se ve (Montevideo a escala país) lleva un anillo que lo elige', async ({ page }, info) => {
	test.skip(info.project.name === 'movil', 'se prueba en escritorio');
	await page.setViewportSize({ width: 1024, height: 768 });
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
	await mapaListo(page);
	type M = { jumpTo(o: { center: [number, number]; zoom: number }): void; once(e: string, f: () => void): void; queryRenderedFeatures(o: { layers: string[] }): { properties: { id: string } }[]; project(p: [number, number]): { x: number; y: number } };
	// A escala país, a 1024 px, Montevideo mide ~43 px de lado (menos de 48): lleva anillo; los demás no.
	await page.waitForFunction(() => {
		const m = (window as unknown as { __mapa: M }).__mapa;
		return m.queryRenderedFeatures({ layers: ['anillo-chicos'] }).some((f) => f.properties.id === 'INE-2023/departamento/01');
	}, undefined, { timeout: 10_000 });
	const anillos = await page.evaluate(() => (window as unknown as { __mapa: M }).__mapa.queryRenderedFeatures({ layers: ['anillo-chicos'] }).map((f) => f.properties.id));
	expect(anillos).toEqual(['INE-2023/departamento/01']);
	// tocar el anillo elige Montevideo
	const mvd = indice.find((t) => t.nivel === 'departamento' && t.codigo === '01')!;
	// un punto del anillo que NO está dentro del polígono de Montevideo (así el clic lo maneja el anillo)
	const punto = await page.evaluate((b) => {
		type Q = M & { getCanvas(): HTMLCanvasElement; queryRenderedFeatures(p: [number, number], o: { layers: string[] }): { properties: { id: string } }[] };
		const m = (window as unknown as { __mapa: Q }).__mapa;
		const c = m.getCanvas().getBoundingClientRect();
		const centro = m.project([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]);
		for (let a = 0; a < 360; a += 15) {
			const x = centro.x + 14 * Math.cos((a * Math.PI) / 180);
			const y = centro.y + 14 * Math.sin((a * Math.PI) / 180);
			const enMvd = m.queryRenderedFeatures([x, y], { layers: ['relleno-departamento'] }).some((f) => f.properties.id === 'INE-2023/departamento/01');
			const enAnillo = m.queryRenderedFeatures([x, y], { layers: ['anillo-chicos'] }).length > 0;
			if (!enMvd && enAnillo) return { x: c.x + x, y: c.y + y };
		}
		return null;
	}, mvd.bbox);
	expect(punto).not.toBeNull();
	await page.mouse.click(punto!.x, punto!.y);
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText('Montevideo');
	// y en el nivel sección no hay anillos de departamentos
	await abrirOpciones(page);
	await nivelRadio(page, 'Sección').check();
	await page.waitForFunction(() => (window as unknown as { __mapa: M }).__mapa.queryRenderedFeatures({ layers: ['anillo-chicos'] }).length === 0);
});

test('AC-V11: el panel muestra la fuente una vez, sin reglas internas, y los botones del mismo ancho', async ({ page }) => {
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	const p = panel(page);
	await expect(p.getByRole('heading', { level: 2 })).toHaveText('Flores');
	await expect(p.getByText(/^Fuente: /)).toHaveCount(1); // el principal y los otros datos son del Censo
	await expect(p).not.toContainText('el observatorio');
	await expect(p).not.toContainText('no suma territorios');
	await expect(p.getByText('Total del país: no publicado por la fuente.')).toBeVisible();
	const [a, b] = await Promise.all([
		p.getByRole('link', { name: 'Ver ficha completa' }).boundingBox(),
		p.getByRole('button', { name: 'Descargar CSV' }).boundingBox()
	]);
	expect(Math.abs(a!.width - b!.width)).toBeLessThanOrEqual(1);
	// cada botón en una sola línea (alto de un botón, no de dos líneas de texto)
	expect(a!.height).toBeLessThan(60);
	expect(b!.height).toBeLessThan(60);
});

test('AC-V13: en celular la vista previa del mapa tiene los colores de la leyenda', async ({ page }, info) => {
	test.skip(info.project.name !== 'movil', 'la vista previa es de celular y tableta');
	for (const ancho of [390, 768]) {
		await page.setViewportSize({ width: ancho, height: 900 });
		await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
		const previa = page.locator('.previa svg.mini'); // decorativa (aria-hidden): el botón «Ver el mapa interactivo» la acompaña
		await expect(previa).toBeVisible();
		const leyenda = page.getByRole('region', { name: 'Leyenda' }).locator('visible=true');
		await expect(leyenda.locator('.muestra').first()).toBeVisible();
		// esperar a que lleguen los valores y se pinte
		await expect.poll(async () => new Set(await previa.locator('path').evaluateAll((ps) => ps.map((p) => getComputedStyle(p).fill))).size).toBeGreaterThan(2);
		const deLaLeyenda = new Set(await leyenda.locator('.muestra').evaluateAll((ms) => ms.map((m) => getComputedStyle(m).backgroundColor)));
		const deLaPrevia = await previa.locator('path').evaluateAll((ps) => ps.map((p) => getComputedStyle(p).fill).filter((f) => f !== 'none'));
		const deptos = (JSON.parse(readFileSync('build/datos-web/uruguay_mini.geojson', 'utf-8')) as { features: { properties: { nivel: string } }[] }).features.filter((f) => f.properties.nivel === 'departamento').length;
		expect(deLaPrevia).toHaveLength(deptos);
		for (const c of deLaPrevia) expect(deLaLeyenda, `${ancho} px: ${c}`).toContain(c);
	}
});

test('AC-V13: en celular el mapa empieza en la primera pantalla; los controles se abren en una hoja', async ({ page }, info) => {
	test.skip(info.project.name !== 'movil', 'diseño de celular');
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023');
	const mapa = page.locator('section[aria-label="Mapa interactivo"]');
	expect((await mapa.boundingBox())!.y).toBeLessThan(844);
	const barra = page.getByRole('button', { name: /Cambiar$/ });
	await expect(barra).toContainText('Personas · Departamento · 2023');
	await expect(barra).toHaveAttribute('aria-expanded', 'false');
	await expect(page.locator('#controles-mapa')).toBeHidden();
	await barra.click();
	await expect(barra).toHaveAttribute('aria-expanded', 'true');
	await expect(page.getByRole('group', { name: 'Nivel territorial' })).toBeVisible();
	// elegir otro nivel actualiza el resumen; Escape cierra y el foco vuelve a la barra
	await nivelRadio(page, 'Sección').check();
	await page.keyboard.press('Escape');
	await expect(page.locator('#controles-mapa')).toBeHidden();
	await expect(barra).toBeFocused();
	await expect(barra).toContainText('Personas · Sección · 2023');
	// al abrir, el foco va al tema elegido; «Listo» cierra y lo devuelve a la barra; axe con la hoja abierta
	await barra.click();
	await expect(page.getByRole('group', { name: 'Tema' }).getByRole('radio', { name: 'Población' })).toBeFocused();
	const graves = (await new AxeBuilder({ page }).analyze()).violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
	expect(graves.map((v) => v.id)).toEqual([]);
	await page.getByRole('button', { name: 'Listo' }).click();
	await expect(page.locator('#controles-mapa')).toBeHidden();
	await expect(barra).toBeFocused();
});

// AC-I20 (F3.7c): solo con datos publicados por región (la vista previa con ingresos o la fuente activa); en el CI
// del fixture no hay, y la prueba se saltea.
test('AC-I20: lo que se publica por región muestra el aviso y la comparación, no el coroplético', async ({ page }) => {
	const indicadores = JSON.parse(readFileSync('build/datos-web/indicadores.json', 'utf-8')) as { codigo: string; niveles: string[] }[];
	const regional = indicadores.find((i) => i.codigo === 'ing_hogar_medio_sagu_svl' && i.niveles.includes('region'));
	test.skip(!regional, 'no hay indicadores publicados por región en estos datos');
	await page.goto('?indicador=ing_hogar_medio_sagu_svl&nivel=departamento&periodo=2026-T3');
	await expect(page.getByText('Los ingresos se publican por región: País · Montevideo · Interior.')).toBeVisible();
	const filas = page.locator('.comparacion li');
	await expect(filas).toHaveCount(5);
	await expect(filas.nth(0)).toContainText('Total país');
	await expect(filas.nth(0)).toContainText('98.653');
	await expect(filas.nth(1)).toContainText('120.938');
	await expect(filas.nth(2)).toContainText('83.651');
	await expect(page.locator('.comparacion figcaption')).toContainText('jul–set 2026');
	await expect(page.locator('section.leyenda')).toHaveCount(0); // sin coroplético
	// en escritorio cada indicador dice dónde se publica (en celular se elige con un desplegable)
	if ((page.viewportSize()?.width ?? 0) > 900) await expect(page.getByText('INE · por región').first()).toBeVisible();
	expect((await new AxeBuilder({ page }).include('.avisos').analyze()).violations).toEqual([]);
});
