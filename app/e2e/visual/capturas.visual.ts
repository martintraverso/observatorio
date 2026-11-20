// M10.10 (#88): capturas de referencia de AC-V31, solo en Chromium (proyectos `visual-1440` … `visual-390`).
//
// - Corren con el fixture (el CI de cada PR). Con los datos completos (el deploy) se saltean: esos datos cambian
//   con cada release de datos y las capturas fallarían sin que nada esté roto.
// - Las referencias (`capturas.visual.ts-snapshots/*-linux.png`) son las del runner de CI: la letra se dibuja
//   distinto en otras máquinas. Para actualizarlas, en un PR con la etiqueta `visual` y capturas antes/después:
//   correr el CI, bajar el artefacto `playwright` de la corrida que falla y copiar los `*-actual.png` como
//   referencias (ver app/README.md).
// - Lo que cambia entre corridas se estabiliza: las fechas se reemplazan por «00/00/0000» y los lienzos de
//   MapLibre (mapa y localizador de cerca) se ocultan con CSS (no con una máscara, que taparía también la
//   leyenda superpuesta): paneles, leyenda y textos quedan en la captura.
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { esperarQuieta } from './ayudas';

const indice = JSON.parse(readFileSync('build/datos-web/territorios_index.json', 'utf-8')) as { nivel: string; codigo: string; depto: string }[];
/** El fixture tiene unos pocos cientos de territorios; los datos completos, más de 5000. */
const ES_FIXTURE = indice.length < 1000;
const SEGMENTO = indice.find((t) => t.nivel === 'segmento' && t.depto === '07')!;

const RUTAS_AC_V31 = [
	{ nombre: 'mapa-departamento', ruta: '?indicador=pob_total&nivel=departamento&periodo=2023' },
	{ nombre: 'mapa-departamento-seleccion', ruta: '?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07' },
	{ nombre: 'mapa-municipio', ruta: '?indicador=pob_total&nivel=municipio_mvd&periodo=2023' },
	{ nombre: 'mapa-segmento', ruta: '?indicador=pob_total&nivel=segmento&periodo=2023' },
	{ nombre: 'ficha-departamento', ruta: 'territorio/departamento/07' },
	{ nombre: 'ficha-segmento', ruta: `territorio/segmento/${SEGMENTO.codigo}` },
	{ nombre: 'fuentes', ruta: 'fuentes' },
	{ nombre: 'datos', ruta: 'datos' }
];

type MapaLibre = { loaded(): boolean; areTilesLoaded(): boolean };

/** Espera a que terminen de dibujarse el mapa y el localizador de cerca, si la página los tiene. */
async function mapasQuietos(page: Page) {
	await page.waitForFunction(
		() => {
			const w = window as unknown as { __mapa?: MapaLibre; __localizador?: MapaLibre };
			const listo = (m?: MapaLibre) => !m || (m.loaded() && m.areTilesLoaded());
			return listo(w.__mapa) && listo(w.__localizador) && !document.querySelector('.cargando[role="status"]');
		},
		undefined,
		{ timeout: 20_000 }
	);
}

/** Las fechas (generación de los datos, capturas) cambian en cada corrida: se reemplazan por un texto fijo. */
async function fechasFijas(page: Page) {
	await page.evaluate(() => {
		const caminante = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
		for (let n = caminante.nextNode(); n; n = caminante.nextNode()) {
			if (n.textContent && /\d{2}\/\d{2}\/\d{4}/.test(n.textContent)) n.textContent = n.textContent.replace(/\d{2}\/\d{2}\/\d{4}/g, '00/00/0000');
		}
	});
}

/** Captura de página completa; los lienzos de MapLibre no se ven, pero paneles y leyenda quedan. */
async function capturar(page: Page, nombre: string) {
	await esperarQuieta(page);
	await mapasQuietos(page);
	await fechasFijas(page);
	await expect(page).toHaveScreenshot(`${nombre}.png`, {
		fullPage: true,
		animations: 'disabled',
		caret: 'hide',
		style: 'canvas.maplibregl-canvas { opacity: 0 !important; }',
		maxDiffPixelRatio: 0.01
	});
}

for (const { nombre, ruta } of RUTAS_AC_V31) {
	test(`AC-V31: captura ${nombre}`, async ({ page }) => {
		test.skip(!ES_FIXTURE, 'las capturas de referencia son del fixture (el CI de cada PR)');
		// AC-V31 pide el mapa por municipio: si el fixture dejara de tenerlo, que falle en vez de faltar la captura
		if (nombre === 'mapa-municipio') expect(indice.some((t) => t.nivel === 'municipio_mvd')).toBe(true);
		await page.goto(ruta);
		await capturar(page, nombre);
	});
}
