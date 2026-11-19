// M10.0 (#78): controles de calidad visual sobre el sitio construido, en las cuatro vistas
// (proyectos `visual-*` de playwright.config.ts). Criterios: docs/ACCEPTANCE_CRITERIA_UI.md.
//
// Los problemas que el `main` todavía tiene están marcados con `pendiente(...)`: el test se
// espera que falle (test.fail) y se pone rojo cuando el problema se corrige, para que la
// historia que lo corrige saque la marca. Así el arnés prueba que detecta cada problema.
import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { nivelesConDatos } from '../../src/lib/mapa/estado.ts';
import { detectarDesbordes, esperarQuieta, revisarSegmentado, sinTextoInterno, TEXTOS_INTERNOS } from './ayudas';

type Territorio = { nivel: string; codigo: string; nombre: string; depto: string };
const indice = JSON.parse(readFileSync('build/datos-web/territorios_index.json', 'utf-8')) as Territorio[];
const fuentes = JSON.parse(readFileSync('build/datos-web/fuentes.json', 'utf-8')) as { id: string }[];
const indicadores = JSON.parse(readFileSync('build/datos-web/indicadores.json', 'utf-8')) as Parameters<typeof nivelesConDatos>[0];
const NIVELES = nivelesConDatos(indicadores);

// Tacuarembó es la ficha de referencia de AC-V18; con el fixture (sin Tacuarembó), Flores.
const DEPTO = indice.find((t) => t.nivel === 'departamento' && t.codigo === '18') ?? indice.find((t) => t.nivel === 'departamento' && t.codigo === '07')!;
const SEGMENTO = indice.find((t) => t.nivel === 'segmento' && t.depto === DEPTO.depto)!;
const fichaDepto = JSON.parse(readFileSync(`build/datos-web/fichas/departamento/${DEPTO.codigo}.json`, 'utf-8')) as {
	capturas: Record<string, { fuente_id: string }>;
};
const capturasDepto = Object.values(fichaDepto.capturas);
const fuentesDepto = new Set(capturasDepto.map((c) => c.fuente_id));

/** Fuentes cuyos datos publicados traen textos internos del mantenedor (V-15). */
const conTextoInterno = new Set(fuentes.filter((f) => TEXTOS_INTERNOS.some((t) => t.test(JSON.stringify(f)))).map((f) => f.id));

/** Vista del proyecto: 'visual-firefox-768' → '768'. */
const vista = (proyecto: string) => proyecto.split('-').at(-1)!;

// `desborda` y `interno`: si en esta ruta el main todavía tiene el problema (V-01, V-15), según los datos y la vista.
const RUTAS: { ruta: string; nombre: string; desborda?: (vista: string) => boolean; interno?: boolean }[] = [
	// «Municipio (Montevideo)» ocupa dos líneas salvo a 768 px, donde el panel es más ancho (M10.1).
	{ ruta: '', nombre: 'Mapa', desborda: (v) => NIVELES.includes('municipio_mvd') && v !== '768' },
	{ ruta: 'fichas', nombre: 'Fichas' },
	{
		ruta: `territorio/departamento/${DEPTO.codigo}`,
		nombre: `Ficha departamento (${DEPTO.nombre})`,
		interno: [...fuentesDepto].some((id) => conTextoInterno.has(id))
	},
	{ ruta: `territorio/segmento/${SEGMENTO.codigo}`, nombre: 'Ficha segmento' },
	{ ruta: 'fuentes', nombre: 'Fuentes' },
	...fuentes.map((f) => ({ ruta: `fuentes/${f.id}`, nombre: `Fuente ${f.id}`, interno: conTextoInterno.has(f.id) })),
	{ ruta: 'datos', nombre: 'Datos' }
];

/** Problema conocido del `main`: el test tiene que fallar hasta que la historia indicada lo corrija. */
function pendiente(condicion: boolean, historia: string) {
	test.fail(condicion, `problema conocido, lo corrige ${historia}`);
}

for (const { ruta, nombre, desborda, interno } of RUTAS) {
	test.describe(nombre, () => {
		test('AC-V5: ningún texto desborda ni queda recortado', async ({ page }, info) => {
			pendiente(!!desborda?.(vista(info.project.name)), 'M10.1 (#79)');
			await page.goto(ruta);
			expect(await detectarDesbordes(page)).toEqual([]);
		});

		test('AC-V19: sin textos internos del mantenedor', async ({ page }) => {
			pendiente(!!interno, 'M10.5 (#83)');
			await page.goto(ruta);
			expect(await sinTextoInterno(page)).toEqual([]);
		});
	});
}

test('AC-V1: el selector «Nivel territorial» muestra las opciones en una fila o en una lista vertical', async ({ page }) => {
	// La grilla fija de 3 columnas deja sola a la cuarta opción (V-01).
	pendiente(NIVELES.length > 3, 'M10.1 (#79)');
	await page.goto('');
	expect(await revisarSegmentado(page, 'fieldset:has(> legend:text-is("Nivel territorial"))')).toEqual([]);
});

test(`AC-V18: «Fuentes de esta ficha» muestra una entrada por fuente (${DEPTO.nombre})`, async ({ page }) => {
	pendiente(capturasDepto.length > fuentesDepto.size, 'M10.5 (#83)');
	await page.goto(`territorio/departamento/${DEPTO.codigo}`);
	await expect(page.locator('#fuentes ul.fuentes > li')).toHaveCount(fuentesDepto.size);
});

test(`AC-V18: largo de la ficha de Tacuarembó`, async ({ page }, info) => {
	const maximo = ({ '1440': 6000, '390': 15000 } as Record<string, number>)[vista(info.project.name)];
	test.skip(!maximo, 'el criterio fija el largo a 1440 y a 390 px');
	test.skip(DEPTO.codigo !== '18', 'el build no trae Tacuarembó (fixture)');
	pendiente(capturasDepto.length > fuentesDepto.size, 'M10.5 (#83)');
	await page.goto(`territorio/departamento/${DEPTO.codigo}`);
	await esperarQuieta(page);
	const alto = await page.evaluate(() => document.documentElement.scrollHeight);
	expect(alto, `${alto} px`).toBeLessThanOrEqual(maximo!);
});
