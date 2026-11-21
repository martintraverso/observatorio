import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { existsSync, readFileSync } from 'node:fs';

const indice = JSON.parse(readFileSync('build/datos-web/territorios_index.json', 'utf-8')) as {
	nivel: string;
	codigo: string;
	nombre: string;
	depto: string;
	padre_id: string | null;
}[];
const de = (nivel: string) => indice.find((t) => t.nivel === nivel && t.depto === '07')!;

test('AC-F1: hay ficha para cada departamento, sección, segmento y localidad', () => {
	const niveles = ['departamento', 'seccion', 'segmento', 'localidad'];
	const faltan = indice
		.filter((t) => niveles.includes(t.nivel))
		.filter((t) => !existsSync(`build/territorio/${t.nivel}/${t.codigo}.html`))
		.map((t) => `${t.nivel}/${t.codigo}`);
	expect(faltan).toEqual([]);
});

test('AC-F2: ficha de departamento con migas, identidad, ubicación, cifras y enlaces', async ({ page }) => {
	await page.goto('territorio/departamento/07');
	await expect(page.getByRole('navigation', { name: 'Ubicación' })).toContainText('Uruguay');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Flores');
	await expect(page.getByText('Código INE 07', { exact: true })).toBeVisible();
	await expect(page.getByRole('img', { name: 'Ubicación de Flores en Uruguay' })).toBeVisible();
	await expect(page.getByText('Personas (2023)').first()).toBeVisible();
	await expect(page.locator('.kpis')).toContainText('26.271');
	// Enlace a un territorio contenido
	const seccion = de('seccion');
	await page.getByRole('tabpanel').getByRole('link', { name: seccion.nombre, exact: true }).click();
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(seccion.nombre);
	// y de vuelta al padre por las migas
	await page.getByRole('navigation', { name: 'Ubicación' }).getByRole('link', { name: 'Flores' }).click();
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Flores');
});

test('AC-F3: ficha de segmento con sus conteos y los de su sección y departamento', async ({ page }) => {
	const seg = de('segmento');
	await page.goto(`territorio/segmento/${seg.codigo}`);
	await expect(page.getByRole('table', { name: `Población en ${seg.nombre}` })).toContainText('personas');
	const contienen = page.getByRole('region', { name: 'Más datos en los niveles que contienen este territorio' });
	await expect(contienen.getByRole('article')).toHaveCount(2);
	await expect(contienen.getByRole('link', { name: 'Flores' })).toBeVisible();
	await expect(contienen).toContainText('26.271 personas');
	await expect(contienen.getByRole('link', { name: /^Sección / })).toBeVisible();
	// proporción del valor publicado sobre el de los niveles que lo contienen
	await expect(page.getByRole('table', { name: `Población en ${seg.nombre}` })).toContainText('% de Flores');
	await expect(page.getByRole('heading', { name: 'Hechos registrados' })).toBeVisible();
});

test('AC-F4: el departamento explica que la suma de secciones no es su total', async ({ page }) => {
	await page.goto('territorio/departamento/07');
	const nota = page.locator('#poblacion .nota');
	await expect(nota).toContainText('La suma de las 6 secciones');
	await expect(nota).toContainText('no coincide con el total del departamento (26.271)');
	await expect(nota).toContainText('registros administrativos');
});

test('AC-F5: el CSV tiene exactamente los valores que muestra la ficha', async ({ page }) => {
	await page.goto('territorio/departamento/07');
	// todas las secciones de temas: con la vista previa (F2.8a) también trae Trabajo
	const filas = page.locator('section.seccion:not(#fuentes) tbody tr');
	const mostradas = await filas.evaluateAll((trs) =>
		trs.map((tr) => [...tr.querySelectorAll('td')].slice(0, 3).map((td) => td.textContent!.trim().replace(/\s+/g, ' ')))
	);
	const [descarga] = await Promise.all([
		page.waitForEvent('download'),
		page.getByRole('button', { name: 'Descargar CSV' }).click()
	]);
	const [cabecera, ...csv] = readFileSync((await descarga.path())!, 'utf-8').replace(/^﻿/, '').trim().split('\r\n');
	expect(cabecera).toBe('territorio_id,nivel,codigo,nombre,indicador,periodo,periodo_inicio,periodo_fin,tipo_periodo,valor,unidad,es_estimado,fuente,archivo_origen,sha256');
	expect(csv).toHaveLength(mostradas.length);
	const es = new Intl.NumberFormat('es-UY', { useGrouping: 'always' });
	for (const linea of csv) {
		const c = linea.split(',');
		const fila = mostradas.find(([, valor, periodo]) => valor === `${es.format(Number(c[9]))} ${c[10]}` && periodo === c[5]);
		expect(fila, linea).toBeTruthy();
		expect(c[0]).toBe('INE-2023/departamento/07');
		if (c[8] === 'censo') {
			expect(c.slice(6, 9)).toEqual(['2023-01-01', '2023-01-01', 'censo']); // AC-L27
			expect(c[13]).toMatch(/\.zip$/);
		} else {
			expect(c[8]).toBe('trimestre_movil'); // ECH, solo en la vista previa
			expect(c[13]).toMatch(/\.html$/);
		}
		expect(c[14]).toMatch(/^[0-9a-f]{64}$/);
	}
});

test('AC-F6: cómo citar incluye observatorio, territorio, fecha de consulta e INE', async ({ page }) => {
	await page.goto('territorio/departamento/07');
	const cita = page.locator('blockquote.cita');
	await expect(cita).toContainText('Observatorio Uruguay');
	await expect(cita).toContainText('«Flores»');
	await expect(cita).toContainText('Instituto Nacional de Estadística (INE)');
	await expect(cita).toContainText(/Consultado el \d\d\/\d\d\/\d{4}\./);
	await expect(cita).toContainText('/observatorio/territorio/departamento/07');
});

test('AC-F7: los temas sin datos lo dicen', async ({ page }) => {
	// los temas sin datos salen de los datos del build (con la vista previa, Trabajo sí tiene)
	const conDatos = new Set(
		(JSON.parse(readFileSync('build/datos-web/indicadores.json', 'utf-8')) as { tema: string }[]).map((i) => i.tema)
	);
	// secciones de la ficha y sus temas (src/lib/ficha/logica.ts): sin datos si ninguno de sus temas tiene
	const secciones: Record<string, string[]> = { trabajo: ['Trabajo', 'Ingresos'], educacion: ['Educación'] };
	const sinDatos = Object.entries(secciones).filter(([, ts]) => !ts.some((t) => conDatos.has(t))).map(([id]) => id);
	expect(sinDatos).toContain('educacion');
	await page.goto('territorio/departamento/07');
	for (const id of sinDatos) {
		await expect(page.locator(`#${id}`)).toContainText('Todavía no hay fuentes cargadas para este tema');
	}
});

test('pestañas de "Dentro de": clic y flechas del teclado', async ({ page }) => {
	await page.goto('territorio/departamento/07');
	const pestanas = page.getByRole('tablist', { name: 'Unidades dentro de Flores' }).getByRole('tab');
	await expect(pestanas.first()).toHaveAttribute('aria-selected', 'true');
	await pestanas.first().focus();
	await page.keyboard.press('ArrowRight');
	await expect(pestanas.nth(1)).toHaveAttribute('aria-selected', 'true');
	await expect(pestanas.nth(1)).toBeFocused();
	await expect(page.getByRole('tabpanel')).toContainText('Segmento');
});

test('ficha de localidad lista sus segmentos y el enlace al mapa conserva el territorio', async ({ page }) => {
	const loc = de('localidad');
	await page.goto(`territorio/localidad/${loc.codigo}`);
	await expect(page.getByRole('tab', { name: /Segmento censal/ })).toBeVisible();
	await page.getByRole('link', { name: 'Ver en el mapa' }).first().click();
	await expect(page).toHaveURL(new RegExp(`territorio=localidad%2F${loc.codigo}|territorio=localidad/${loc.codigo}`));
});

test('el límite contestado avisa que no tiene datos propios', async ({ page }) => {
	await page.goto('territorio/area_especial/02-limite-contestado');
	await expect(page.getByText('Este polígono no tiene datos propios')).toBeVisible();
});

for (const nivel of ['segmento', 'localidad', 'seccion']) {
	test(`accesibilidad de la ficha de ${nivel} (axe)`, async ({ page }) => {
		await page.goto(`territorio/${nivel}/${de(nivel).codigo}`);
		const { violations } = await new AxeBuilder({ page }).analyze();
		const graves = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
		expect(graves.map((v) => `${v.id}: ${v.nodes.length} nodos`)).toEqual([]);
	});
}

test('AC-L17 y AC-L28: el país y los municipios de Montevideo tienen ficha', async ({ page }) => {
	const deptos = indice.filter((t) => t.nivel === 'departamento').length;
	await page.goto('fichas');
	await page.getByRole('link', { name: 'Uruguay', exact: true }).last().click();
	await expect(page).toHaveURL(/territorio\/pais\/UY$/);
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Uruguay');
	await expect(page.getByText('País', { exact: true })).toBeVisible();
	await expect(page.getByRole('tab', { name: `Departamento (${deptos})` })).toBeVisible();

	await page.goto('territorio/departamento/07');
	await expect(page.getByText('Pertenece al país:')).toContainText('Uruguay');

	const mun = indice.filter((t) => t.nivel === 'municipio_mvd');
	expect(mun.map((t) => t.codigo).sort()).toEqual(['A', 'B', 'C', 'CH', 'D', 'E', 'F', 'G']);
	await page.goto('territorio/municipio_mvd/CH');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Municipio CH');
	await expect(page.getByRole('navigation', { name: 'Ubicación' })).toContainText('Montevideo');
	const ccz = indice.filter((t) => t.nivel === 'ccz_mvd' && t.nombre.endsWith('(Municipio CH)'));
	await expect(page.getByRole('tab', { name: `CCZ (Montevideo) (${ccz.length})` })).toBeVisible();
	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

	await page.goto(`territorio/ccz_mvd/${ccz[0].codigo}`);
	await expect(page.getByText('Pertenece al municipio:')).toContainText('Municipio CH');
});

test('AC-V24: si un tema no se publica al nivel de la ficha, enlaza al nivel que lo contiene y lo publica', async ({ page }) => {
	// Las secciones de la ficha y sus temas (SECCIONES_FICHA en src/lib/ficha/logica.ts).
	const SECCIONES_FICHA = [
		{ id: 'poblacion', temas: ['Población'] },
		{ id: 'vivienda', temas: ['Vivienda', 'Hogares'] },
		{ id: 'trabajo', temas: ['Trabajo', 'Ingresos'] },
		{ id: 'educacion', temas: ['Educación'] }
	];
	// Un segmento de San José (con datos completos su departamento tiene la ECH); si no está, uno de Flores.
	const seg = indice.find((t) => t.nivel === 'segmento' && t.depto === '16') ?? de('segmento');
	const f = JSON.parse(readFileSync(`build/datos-web/fichas/segmento/${seg.codigo}.json`, 'utf-8')) as {
		padres: { nivel: string; nombre: string; valores: Record<string, unknown> }[];
		indicadores: Record<string, { tema: string }>;
		observaciones: { indicador: string }[];
	};
	await page.goto(`territorio/segmento/${seg.codigo}`);
	let enPadre = 0;
	for (const s of SECCIONES_FICHA) {
		const temas = s.temas;
		const propios = f.observaciones.some((o) => temas.includes(f.indicadores[o.indicador]?.tema));
		if (propios) continue;
		const padre = [...f.padres].reverse().find((p) => Object.keys(p.valores).some((k) => temas.includes(f.indicadores[k]?.tema)));
		const seccion = page.locator(`section#${s.id}`);
		if (padre) {
			enPadre++;
			await expect(seccion).toContainText(`se publica por ${padre.nivel}`);
			await expect(seccion.getByRole('link', { name: `ver ${padre.nombre}` })).toHaveAttribute('href', new RegExp(`/territorio/${padre.nivel}/\\w+#${s.id}$`));
			await expect(seccion).not.toContainText('Todavía no hay fuentes cargadas');
		} else {
			await expect(seccion).toContainText('Todavía no hay fuentes cargadas para este tema.');
		}
	}
	// Con datos completos la ECH (Trabajo) está por departamento y no por segmento: tiene que aparecer el enlace.
	const hayEch = Object.values(f.indicadores).some((i) => i.tema === 'Trabajo');
	expect(enPadre > 0).toBe(hayEch);
	if (hayEch && seg.depto === '16') {
		// el caso del hallazgo V-19, literal
		await expect(page.locator('section#trabajo')).toContainText('Trabajo: se publica por departamento');
		await expect(page.locator('section#trabajo').getByRole('link', { name: 'ver San José' })).toBeVisible();
	}
});

test('AC-V22: información, advertencia y error tienen estilos distintos y se usan según el tipo de mensaje', async ({ page }) => {
	await page.goto('territorio/departamento/07');
	// explicaciones y «todavía no hay…»: información (azul), no advertencia
	await expect(page.locator('#poblacion .nota')).toHaveClass(/\binfo\b/);
	await expect(page.locator('#educacion .vacio')).toHaveClass(/\binfo\b/);
	await expect(page.locator('section .aviso')).toHaveCount(0);
	const fondo = (sel: string) => page.locator(sel).first().evaluate((el) => getComputedStyle(el).backgroundColor);
	const info = await fondo('#poblacion .nota');
	// algo que no existe: error (rojo)
	await page.goto('./?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/99');
	const error = page.getByRole('complementary', { name: 'Territorio seleccionado' }).getByRole('alert');
	await expect(error).toBeVisible(); // también en celular (la hoja se abre con el error)
	await expect(error).toContainText('No encontramos ese territorio.');
	await expect(error).toHaveClass(/\berror\b/);
	const rojo = await error.evaluate((el) => getComputedStyle(el).backgroundColor);
	// la advertencia (naranja) sigue existiendo para lo que se puede malinterpretar
	const naranja = await page.evaluate(() => {
		const p = document.createElement('p');
		p.className = 'aviso';
		document.body.append(p);
		const c = getComputedStyle(p).backgroundColor;
		p.remove();
		return c;
	});
	expect(new Set([info, rojo, naranja]).size).toBe(3);
	// y se puede cerrar
	await error.getByRole('button', { name: 'Cerrar' }).click();
	await expect(error).toHaveCount(0);
	await expect(page).not.toHaveURL(/territorio=/);
});

test('AC-V26: las fichas de segmento, sección y localidad muestran la unidad de cerca entre sus vecinos', async ({ page }, info) => {
	test.skip(!['escritorio', 'movil'].includes(info.project.name), 'el mapa de cerca necesita WebGL (Chromium)');
	type L = { loaded(): boolean; areTilesLoaded(): boolean; queryRenderedFeatures(o: { layers: string[] }): { properties: { id: string } }[] };
	// además del urbano, el segmento de caja más grande (rural): no puede quedar en blanco por el zoom mínimo del PMTiles
	const area = (t: { bbox: number[] }) => (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]);
	const rural = (indice as unknown as { nivel: string; codigo: string; nombre: string; depto: string; bbox: number[] }[])
		.filter((t) => t.nivel === 'segmento')
		.sort((a, b) => area(b) - area(a))[0];
	const casos = [
		de('segmento'),
		rural,
		de('seccion'),
		indice.find((t) => t.nivel === 'localidad' && existsSync(`build/territorio/localidad/${t.codigo}.html`))!
	].filter(Boolean);
	for (const t of casos) {
		await page.goto(`territorio/${t.nivel}/${t.codigo}`);
		const cerca = page.getByRole('img', { name: `${t.nombre} y sus vecinos, de cerca` });
		await cerca.scrollIntoViewIfNeeded();
		await expect(cerca).toBeVisible();
		await page.waitForFunction(() => {
			const m = (window as unknown as { __localizador?: L }).__localizador;
			return !!m && m.loaded() && m.areTilesLoaded();
		}, undefined, { timeout: 20_000 });
		const { propio, vecinos } = await page.evaluate((id) => {
			const m = (window as unknown as { __localizador: L & { getLayer(id: string): unknown } }).__localizador;
			// un segmento rural grande se marca con el rectángulo que ocupa (cerca-caja); los demás, con su polígono
			const marca = m.getLayer('cerca-caja')
				? m.queryRenderedFeatures({ layers: ['cerca-caja'] }).length
				: m.queryRenderedFeatures({ layers: ['cerca-seleccion'] }).filter((f) => f.properties.id === id).length;
			return {
				propio: marca,
				vecinos: new Set(m.queryRenderedFeatures({ layers: ['cerca-vecinos'] }).map((f) => f.properties.id)).size
			};
		}, `INE-2023/${t.nivel}/${t.codigo}`);
		expect(propio, t.nivel).toBeGreaterThan(0);
		// con vecinos alrededor (para una localidad, las secciones que la rodean)
		expect(vecinos, t.nivel).toBeGreaterThan(1);
	}
	// los departamentos no lo llevan
	await page.goto('territorio/departamento/07');
	await expect(page.getByRole('img', { name: /de cerca/ })).toHaveCount(0);
});

test('AC-V27: cada KPI dice de dónde sale y la ficha de departamento trae la densidad, marcada como calculada', async ({ page }) => {
	const f = JSON.parse(readFileSync('build/datos-web/fichas/departamento/07.json', 'utf-8')) as {
		area_km2: number;
		observaciones: { indicador: string; periodo: string; valor: number }[];
	};
	const personas = f.observaciones.find((o) => o.indicador === 'pob_total' && o.periodo === '2023')!.valor;
	const esperado = new Intl.NumberFormat('es-UY', { minimumFractionDigits: 1, maximumFractionDigits: 1, useGrouping: 'always' }).format(personas / f.area_km2);
	await page.goto('territorio/departamento/07');
	const kpi = page.locator('.kpis div').filter({ hasText: 'Densidad' });
	await expect(kpi.locator('dt')).toContainText('calculada');
	await expect(kpi.locator('dd')).toContainText(`${esperado} pers./km²`);
	const notas = page.locator('.notas-kpi');
	await expect(notas).toContainText('Personas y viviendas: INE · Unidades geoestadísticas Censo 2023');
	await expect(notas).toContainText('Superficie y localidades: a partir de la geometría del INE');
	await expect(notas).toContainText('Densidad: calculada por el observatorio');
	// no es una observación: no está en la tabla de indicadores (el CSV sale de las observaciones)
	expect(await page.locator('section.seccion tbody').allTextContents()).not.toContainEqual(expect.stringContaining('Densidad'));
	// solo en los departamentos
	await page.goto(`territorio/segmento/${de('segmento').codigo}`);
	await expect(page.locator('.kpis')).not.toContainText('Densidad');
	await expect(page.locator('.notas-kpi')).toContainText('Superficie');
});

test('AC-I23 y AC-I22: la ficha de región explica qué es; sin ingresos publicados, no hay enlace a una ficha vacía', async ({ page }) => {
	await page.goto('territorio/region/interior-5000');
	const desc = page.locator('.descripcion-region');
	await expect(desc).toContainText('Las localidades de 5.000 o más habitantes de todos los departamentos salvo Montevideo.');
	await expect(desc.getByRole('link', { name: 'Uruguay' })).toHaveAttribute('href', /territorio\/pais\/UY$/);
	await expect(desc.getByRole('link', { name: 'Montevideo' })).toHaveAttribute('href', /territorio\/departamento\/01$/);
	await expect(page.locator('.ubicacion')).toHaveCount(0);
	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
	// los ingresos de la app vienen solo de fuentes activas: mientras estén «en preparación», Flores no enlaza al Interior
	await page.goto('territorio/departamento/07');
	await expect(page.locator('.en-region')).toHaveCount(0);
});
