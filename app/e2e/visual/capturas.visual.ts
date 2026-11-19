// M10.0 (#78): capturas de referencia de AC-V31, solo en Chromium (proyectos `visual-1440` … `visual-390`).
// Las baselines se toman recién en M10.10 (#88), después de corregir los problemas de M10.1–M10.9:
// hasta entonces estos tests quedan en `fixme`. Para tomarlas: sacar el fixme y correr
// `npx playwright test --project='visual-1*' --project='visual-7*' --project='visual-3*' capturas --update-snapshots`
// en un PR con la etiqueta `visual` y las imágenes antes/después.
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { esperarQuieta } from './ayudas';

const indice = JSON.parse(readFileSync('build/datos-web/territorios_index.json', 'utf-8')) as { nivel: string; codigo: string; depto: string }[];
const SEGMENTO = indice.find((t) => t.nivel === 'segmento' && t.depto === '07')!;
const MUNICIPIO = indice.some((t) => t.nivel === 'municipio_mvd') ? 'municipio_mvd' : null;

const RUTAS_AC_V31 = [
	{ nombre: 'mapa-departamento', ruta: '?indicador=pob_total&nivel=departamento&periodo=2023' },
	{ nombre: 'mapa-departamento-seleccion', ruta: '?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07' },
	...(MUNICIPIO ? [{ nombre: 'mapa-municipio', ruta: `?nivel=${MUNICIPIO}` }] : []),
	{ nombre: 'mapa-segmento', ruta: '?indicador=pob_total&nivel=segmento&periodo=2023' },
	{ nombre: 'ficha-departamento', ruta: 'territorio/departamento/07' },
	{ nombre: 'ficha-segmento', ruta: `territorio/segmento/${SEGMENTO.codigo}` },
	{ nombre: 'fuentes', ruta: 'fuentes' },
	{ nombre: 'datos', ruta: 'datos' }
];

/** Captura de página completa; el lienzo del mapa (teselas) se enmascara, pero paneles y leyenda quedan. */
async function capturar(page: Page, nombre: string) {
	await esperarQuieta(page);
	await expect(page).toHaveScreenshot(`${nombre}.png`, {
		fullPage: true,
		animations: 'disabled',
		mask: [page.locator('canvas.maplibregl-canvas')],
		maxDiffPixelRatio: 0.01
	});
}

for (const { nombre, ruta } of RUTAS_AC_V31) {
	test(`AC-V31: captura ${nombre}`, async ({ page }) => {
		test.fixme(true, 'las baselines se toman en M10.10 (#88)');
		await page.goto(ruta);
		await capturar(page, nombre);
	});
}
