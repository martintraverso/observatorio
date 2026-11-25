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
	expect(cabecera).toBe('territorio_id,nivel,codigo,nombre,indicador,periodo,periodo_inicio,periodo_fin,tipo_periodo,valor,unidad,es_estimado,fuente,archivo_origen,sha256,cuadro,es_derivado');
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
	// AC-I22: Flores enlaza al Interior solo si el Interior tiene ingresos en estos datos (con el fixture, no)
	const flores = JSON.parse(readFileSync('build/datos-web/fichas/departamento/07.json', 'utf-8'));
	await page.goto('territorio/departamento/07');
	await expect(page.locator('.en-region')).toHaveCount(flores.region?.temas.includes('Ingresos') ? 1 : 0);
});

test('AC-I22: con ingresos en el Interior, un departamento que no es Montevideo enlaza a la región', async ({ page }) => {
	// Simula la fuente activa: la ficha de Flores llega con la región y el tema Ingresos. Se navega desde la ficha
	// del Interior para que la app pida el JSON (la carga directa viene prerenderizada).
	await page.route('**/datos-web/fichas/departamento/07.json', async (route) => {
		const r = await route.fetch();
		const f = await r.json();
		await route.fulfill({ response: r, json: { ...f, region: { ...f.region, temas: ['Ingresos'] } } });
	});
	await page.goto('territorio/region/interior');
	await page.getByRole('tab', { name: /^Departamento/ }).click();
	await page.getByRole('link', { name: 'Flores', exact: true }).first().click();
	await expect(page).toHaveURL(/territorio\/departamento\/07$/);
	const aviso = page.locator('#trabajo .en-region');
	await expect(aviso).toHaveText('Ingresos: se publican para el Interior del país → ver Interior del país');
	await expect(aviso.getByRole('link')).toHaveAttribute('href', /territorio\/region\/interior#trabajo$/);
	await expect(page.locator('#trabajo')).not.toContainText('Todavía no hay fuentes cargadas');
});

test('AC-I21 y AC-I24: la serie de ingresos con su variante, base de precios, frecuencia y notas', async ({ page }) => {
	// La ficha del Interior con los ingresos reales de 2024–2026 (la fuente está «en preparación» y no llega a la
	// app): se intercepta el JSON y se navega desde el país para que la app lo pida.
	const conIngresos = JSON.parse(readFileSync('e2e/fixtures/ficha-region-interior-ingresos.json', 'utf-8'));
	await page.route('**/datos-web/fichas/region/interior.json', (route) => route.fulfill({ json: conIngresos }));
	await page.goto('territorio/pais/UY');
	await page.getByRole('tab', { name: /^Región/ }).click();
	await page.getByRole('link', { name: 'Interior del país', exact: true }).first().click();
	await expect(page).toHaveURL(/territorio\/region\/interior$/);

	const ingresos = page.locator('#trabajo .ingresos');
	// por defecto, la variante titular del INE: hogares, sin aguinaldo ni valor locativo, precios corrientes, trimestres
	await expect(ingresos.getByRole('radio', { name: 'De los hogares' })).toBeChecked();
	await expect(ingresos.getByRole('checkbox', { name: 'Aguinaldo' })).not.toBeChecked();
	await expect(ingresos.locator('.nombre-serie')).toHaveText(
		'Ingreso medio de los hogares (sin aguinaldo, sin valor locativo, a precios corrientes)'
	);
	await expect(ingresos.locator('.ultimo')).toContainText('jul–set 2026');
	await expect(ingresos.locator('.ultimo')).toContainText('83.651');
	// AC-I24: base de precios y período, fuente, revisión y YDA
	const notas = ingresos.locator('.notas-ingresos');
	await expect(notas).toContainText('pesos corrientes por mes · jul–set 2026');
	await expect(notas).toContainText('Fuente: INE, Encuesta Continua de Hogares');
	await expect(notas).toContainText('sujetas a revisión');
	await expect(notas).toContainText('ingreso disponible ajustado (YDA)');

	// per cápita, con aguinaldo: otra serie
	await ingresos.getByRole('radio', { name: 'Per cápita' }).check();
	await ingresos.getByRole('checkbox', { name: 'Aguinaldo' }).check();
	await expect(ingresos.locator('.nombre-serie')).toContainText('per cápita de los hogares (con aguinaldo, sin valor locativo');
	await expect(ingresos.locator('.ultimo')).toContainText('30.889'); // ECHING13, Interior, jul–set 2026 (sin aguinaldo: 28.878)
	// a precios de enero de 2005: aguinaldo y valor locativo quedan fijos (el INE publica solo esa variante)
	await ingresos.getByRole('radio', { name: 'De enero de 2005' }).check();
	await expect(ingresos.getByRole('checkbox', { name: 'Aguinaldo' })).toBeDisabled();
	// lo que se ve coincide con la serie: sin aguinaldo ni valor locativo
	await expect(ingresos.getByRole('checkbox', { name: 'Aguinaldo' })).not.toBeChecked();
	await expect(ingresos.getByRole('checkbox', { name: 'Valor locativo' })).not.toBeChecked();
	await expect(ingresos.locator('.nombre-serie')).toContainText('(sin aguinaldo, sin valor locativo, a precios de enero de 2005)');
	await expect(notas).toContainText('pesos de enero de 2005 por mes');
	// al volver a precios corrientes vuelve la preferencia (con aguinaldo)
	await ingresos.getByRole('radio', { name: 'Corrientes' }).check();
	await expect(ingresos.getByRole('checkbox', { name: 'Aguinaldo' })).toBeChecked();
	// totales anuales
	await ingresos.getByRole('radio', { name: 'Totales anuales' }).check();
	await expect(ingresos.locator('.ultimo')).toContainText('2025');
	await expect(notas).toContainText('promedio de sus cuatro trimestres');
	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

// F4.7b1 (#210): la educación de una ficha de departamento, una fila por cuadro con el detalle plegado. La fuente del
// MEC está «en preparación» y no llega a la app: se suman a la ficha de Flores dos cuadros reales de 2023–2024.
const EDUCACION = JSON.parse(readFileSync('e2e/fixtures/ficha-educacion-flores.json', 'utf-8'));

/** #227: la ficha avisa que tiene educación (`educacion: true`) y la educación llega aparte, en `educacion.json`. */
async function conEducacion(page: import('@playwright/test').Page, ficha: string, parte: unknown) {
	await page.route(`**/datos-web/fichas/${ficha}.json`, async (route) => {
		const r = await route.fetch();
		await route.fulfill({ response: r, json: { ...(await r.json()), educacion: true } });
	});
	await page.route(`**/datos-web/fichas/${ficha}/educacion.json`, (route) => route.fulfill({ json: parte }));
}

/**
 * Se navega desde /fichas para que la app pida el JSON (la carga directa viene prerenderizada). No desde la ficha del
 * país: con la vista previa, al bajar hasta «Flores» se pasa por su educación, que se carga y corre el enlace (#227).
 */
async function irAFlores(page: import('@playwright/test').Page) {
	await page.goto('fichas');
	await page.getByRole('link', { name: 'Flores', exact: true }).first().click();
	await expect(page).toHaveURL(/territorio\/departamento\/07$/);
}

async function floresConEducacion(page: import('@playwright/test').Page) {
	await conEducacion(page, 'departamento/07', EDUCACION);
	await irAFlores(page);
	// #227: la educación se pide cuando la sección se acerca a la pantalla
	await page.locator('#educacion').scrollIntoViewIfNeeded();
}

test('AC-E27 y AC-E29: la sección «Educación» de un departamento, por nivel, grupo y cuadro, con fuente y notas', async ({ page, browserName }) => {
	await floresConEducacion(page);
	const s = page.locator('#educacion');
	await expect(s.getByRole('heading', { name: 'Primaria', level: 3 })).toBeVisible();
	await expect(s.getByRole('heading', { name: 'Estudiantes', level: 4 })).toBeVisible();
	const cuadro = (c: string) => s.locator('.cuadro').filter({ has: page.locator('.fuente', { hasText: new RegExp(`cuadro ${c.replaceAll('.', '\\.')}$`) }) });
	const matricula = cuadro('II-2.2.1');
	// el total publicado del último año, con unidad y año, y la fuente con el anuario y el cuadro (AC-E29)
	await expect(matricula.locator('.valor')).toContainText('2.112 estudiantes');
	await expect(matricula.locator('.valor')).toContainText('2024');
	await expect(matricula.locator('.fuente')).toHaveText('Fuente: MEC, Anuario Estadístico de Educación 2024, cuadro II-2.2.1');
	// el detalle (aperturas y notas del cuadro) está plegado
	const detalle = matricula.locator('details');
	await expect(detalle.locator('.nota')).toBeHidden();
	await detalle.locator('summary').click();
	await expect(detalle.locator('.nota')).toContainText('Pública no incluye JI');
	await expect(detalle.locator('.aperturas li').filter({ hasText: '% en privada' })).toContainText('calculado por el observatorio');
	// en rendimiento, el resumen es la tasa de promoción calculada por el observatorio
	const rendimiento = cuadro('II-2.2.13');
	await expect(rendimiento.locator('.valor')).toContainText('99,78 %');
	await expect(rendimiento.locator('.valor .calculado')).toHaveText('calculado por el observatorio');
	await expect(s).not.toContainText('Todavía no hay fuentes cargadas');
	// axe, salvo en Firefox: ahí la página con la ficha inyectada por `route` se cae a veces dentro de axe («Page crashed»),
	// también sin dibujar esta sección (probado en local, ver el PR #215). Chromium y WebKit sí lo corren.
	if (browserName !== 'firefox') expect((await new AxeBuilder({ page }).include('#educacion').analyze()).violations).toEqual([]);
});

test('AC-E28: una sección dentro de un departamento con educación dice «Educación: datos por departamento»', async ({ page }) => {
	// La sección llega con su departamento (padre) con un valor de educación, como cuando la fuente esté activa.
	// #227: los valores de educación del departamento van aparte; el padre avisa que los tiene (`educacion: true`)
	await page.route('**/datos-web/fichas/seccion/*.json', async (route) => {
		const r = await route.fetch();
		const f = await r.json();
		const padres = f.padres.map((p: { nivel: string }) => (p.nivel === 'departamento' ? { ...p, educacion: true } : p));
		await route.fulfill({ response: r, json: { ...f, padres } });
	});
	await page.goto('territorio/departamento/07');
	await page.getByRole('tab', { name: /^Sección/ }).click();
	await page.locator('#dentro').getByRole('link').first().click();
	await expect(page).toHaveURL(/territorio\/seccion\//);
	const aviso = page.locator('#educacion .en-padre');
	await expect(aviso).toHaveText('Educación: datos por departamento → ver Flores');
	await expect(aviso.getByRole('link')).toHaveAttribute('href', /territorio\/departamento\/07#educacion$/);
});

test('AC-E27 y AC-E30: cada cuadro con su serie 2020–2024; si cambia de concepto, dos tramos sin unir y la nota', async ({ page }) => {
	await floresConEducacion(page);
	const s = page.locator('#educacion');
	const cuadro = (c: string) => s.locator('.cuadro').filter({ has: page.locator('.fuente', { hasText: new RegExp(`cuadro ${c.replaceAll('.', '\\.')}$`) }) });
	// matrícula de primaria: una sola línea con los cinco años
	const matricula = cuadro('II-2.2.1').locator('.mini-serie');
	await expect(matricula.locator('polyline')).toHaveCount(1);
	await expect(matricula.locator('circle')).toHaveCount(5);
	await expect(matricula.locator('svg')).toHaveAttribute('aria-label', /^Evolución: 2020: 2\.145 estudiantes;.*2024: 2\.112 estudiantes$/);
	await expect(matricula.locator('figcaption')).toHaveText('2020–2024');
	// establecimientos de media básica: hasta 2022 sin privados, desde 2023 con privados (AC-E13): dos tramos y la nota
	const media = cuadro('II-3.1.1').locator('.mini-serie');
	await expect(media.locator('polyline')).toHaveCount(2);
	await expect(media.locator('polyline.otro')).toHaveCount(1);
	await expect(media.locator('svg')).toHaveAttribute('aria-label', /serie cortada/);
	await expect(media.locator('figcaption')).toContainText('Serie cortada: hasta 2022 el total no incluye privados; desde 2023 sí');
});

test('AC-E27 (país): la serie de matrícula 2002–2024 empieza por el total del sistema, y los cuadros B y C van por nivel', async ({ page }) => {
	// La ficha del país con tres series nacionales y un cuadro de tipo B (II-3.2.1), reales, de la vista previa.
	const E = JSON.parse(readFileSync('e2e/fixtures/ficha-educacion-pais.json', 'utf-8'));
	await conEducacion(page, 'pais/UY', E);
	// se navega desde /fichas para que la app pida el JSON: la carga directa viene prerenderizada, y otras fichas (el
	// Interior, un departamento con la ECH) ya piden la del país al cargar y la guardan en la caché
	await page.goto('fichas');
	await page.getByRole('link', { name: 'Uruguay', exact: true }).last().click();
	await expect(page).toHaveURL(/territorio\/pais\/UY$/);
	const s = page.locator('#educacion');
	await s.scrollIntoViewIfNeeded(); // #227: la educación se pide al ver la sección
	const selector = s.getByRole('combobox').first();
	await expect(selector.locator('option:checked')).toHaveText('Matrícula del sistema educativo: TOTAL SISTEMA');
	await expect(selector.locator('option')).toHaveText([
		'Matrícula del sistema educativo: TOTAL SISTEMA',
		'Matrícula del sistema educativo: Total Educación Primaria',
		'Matrícula del sistema educativo: CENFORES - INAU'
	]);
	// la tabla de la serie va de 2002 a 2024 con el total del sistema
	await expect(s.locator('table')).toContainText('2002');
	await expect(s.locator('table')).toContainText('1.042.564');
	// el cuadro de tipo B (media básica, estudiantes) con su fila, bajo su nivel educativo
	const media = s.locator('.nivel-educativo').filter({ has: page.getByRole('heading', { name: 'Media básica', level: 3 }) });
	await expect(media.locator('.fuente', { hasText: 'cuadro II-3.2.1' })).toHaveCount(1);
});

test('AC-E32: el catálogo de educación lista cada cuadro con código, título, tipo, años y dónde se ve', async ({ page }) => {
	const catalogo = JSON.parse(readFileSync('build/datos-web/educacion_catalogo.json', 'utf-8')) as {
		cuadro: string;
		tipo: string;
		departamental: boolean;
		mapa: string | null;
	}[];
	await page.goto('educacion');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Catálogo de educación');
	if (!catalogo.length) {
		// sin la fuente del MEC activa (CI del fixture, sitio publicado hasta #222)
		await expect(page.getByText('Todavía no hay cuadros de educación publicados en el sitio.')).toBeVisible();
		return;
	}
	const filas = page.locator('tbody tr');
	await expect(filas).toHaveCount(catalogo.length);
	// a propósito: uno por departamento, uno nacional y uno con tasa en el mapa (revisión de #234)
	const elegidos = [
		catalogo.find((c) => c.departamental),
		catalogo.find((c) => !c.departamental),
		catalogo.find((c) => c.mapa)
	].filter((c) => c !== undefined);
	for (const c of elegidos) {
		const fila = filas.filter({ has: page.getByRole('cell', { name: c.cuadro, exact: true }) });
		await expect(fila).toHaveCount(1);
		await expect(fila.getByRole('link', { name: `Ficha del país (${c.cuadro})` })).toBeVisible();
		await expect(fila.getByRole('link', { name: `Fichas de departamento (${c.cuadro})` })).toHaveCount(c.departamental ? 1 : 0);
		await expect(fila.getByRole('link', { name: `Mapa (${c.cuadro})` })).toHaveCount(c.mapa ? 1 : 0);
		if (c.mapa) await expect(fila.getByRole('link', { name: `Mapa (${c.cuadro})` })).toHaveAttribute('href', new RegExp(`indicador=${c.mapa}$`));
	}
	await expect(page.getByRole('cell', { name: /^[ABC]?$/ })).toHaveCount(0); // ninguna celda vacía (tipo null, #234)
	expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test('#227: la educación llega aparte: «Cargando…», y si falla lo dice sin romper la página y se puede reintentar', async ({ page }) => {
	let falla = true;
	await page.route('**/datos-web/fichas/departamento/07.json', async (route) => {
		const r = await route.fetch();
		await route.fulfill({ response: r, json: { ...(await r.json()), educacion: true } });
	});
	let liberar = () => {};
	const espera = new Promise<void>((ok) => (liberar = ok));
	await page.route('**/datos-web/fichas/departamento/07/educacion.json', async (route) => {
		await espera;
		if (falla) await route.abort();
		else await route.fulfill({ json: EDUCACION });
	});
	await irAFlores(page);
	const s = page.locator('#educacion');
	await s.scrollIntoViewIfNeeded();
	await expect(s.getByRole('status')).toHaveText('Cargando…');
	liberar();
	await expect(s.getByRole('alert')).toContainText('No se pudo cargar la educación de esta ficha.');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Flores'); // el resto de la ficha sigue
	falla = false;
	await s.getByRole('button', { name: 'Reintentar' }).click();
	await expect(s.getByRole('heading', { name: 'Primaria', level: 3 })).toBeVisible();
	await expect(s.getByRole('alert')).toHaveCount(0);
});

test('#227 y AC-F5: el CSV de la ficha trae la educación aunque la sección no se haya visto', async ({ page }) => {
	await conEducacion(page, 'departamento/07', EDUCACION);
	await irAFlores(page); // sin bajar a la sección
	await expect(page.locator('#educacion').getByRole('heading', { name: 'Primaria', level: 3 })).toHaveCount(0);
	const [descarga] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Descargar CSV' }).click()]);
	const filas = readFileSync((await descarga.path())!, 'utf-8').trim().split('\r\n').slice(1);
	const edu = filas.filter((l) => l.split(',')[4].startsWith('edu_'));
	expect(edu).toHaveLength(EDUCACION.observaciones.length);
});

test('#227: la página prerenderizada de una ficha no incrusta la educación', async ({ request }) => {
	for (const ruta of ['territorio/departamento/07', 'territorio/pais/UY']) {
		const html = (await (await request.get(ruta)).text());
		expect(html, ruta).not.toMatch(/edu_ii_\d/);
	}
});
