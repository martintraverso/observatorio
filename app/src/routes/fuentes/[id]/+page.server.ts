import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { error } from '@sveltejs/kit';
import { CARPETA_DATOS, type EntradaIndice, type Fuente } from '#lib/datos.ts';
import { historialDe, type CapturaHistorial } from '#lib/fuentes.ts';
import type { IndicadorMapa } from '#lib/mapa/estado.ts';
import { leerDatos } from '#lib/server/datos-build.ts';
import type { EntryGenerator, PageServerLoad } from './$types';

// Una página por fuente del registro (fuentes/*.yml).
export const entries: EntryGenerator = () => leerDatos<Fuente[]>('fuentes.json').map((f) => ({ id: f.id }));

export const load: PageServerLoad = ({ params }) => {
	const fuente = leerDatos<(Fuente & { archivo_original?: string })[]>('fuentes.json').find((f) => f.id === params.id);
	if (!fuente) error(404, `No hay una fuente «${params.id}».`);
	const indice = leerDatos<EntradaIndice[]>('territorios_index.json');
	const territoriosPorNivel = Object.fromEntries(
		fuente.niveles_publicados.map((n) => [n, indice.filter((t) => t.nivel === n).length])
	);
	const indicadores = leerDatos<(IndicadorMapa & { cuadro?: string })[]>('indicadores.json').filter((i) => i.fuente_id === fuente.id);
	// #222: el anuario del MEC aporta miles de indicadores (uno por columna y categoría de cada cuadro): la página los
	// resume por cuadro, con el título del catálogo de educación, en lugar de listarlos uno por uno (pesaba varios MB).
	const porCuadro = new Map<string, { n: number; periodos: Set<string> }>();
	for (const i of indicadores) {
		if (!i.cuadro) continue;
		const c = porCuadro.get(i.cuadro) ?? { n: 0, periodos: new Set<string>() };
		c.n++;
		i.periodos.forEach((x) => c.periodos.add(x));
		porCuadro.set(i.cuadro, c);
	}
	const titulos = new Map(
		(existsSync(resolve('static', CARPETA_DATOS, 'educacion_catalogo.json'))
			? leerDatos<{ cuadro: string; titulo: string }[]>('educacion_catalogo.json')
			: []
		).map((c) => [c.cuadro, c.titulo])
	);
	const orden = (c: string) => c.slice(3).split('.').map(Number);
	const cuadros = [...porCuadro]
		.sort(([a], [b]) => {
			const [x, y] = [orden(a), orden(b)];
			return x.reduce((d, v, k) => d || v - (y[k] ?? 0), 0);
		})
		.map(([cuadro, c]) => ({ cuadro, titulo: titulos.get(cuadro) ?? '', indicadores: c.n, periodos: [...c.periodos].sort() }));
	return {
		fuente,
		historial: historialDe(leerDatos<{ historial: CapturaHistorial[] }>('capturas.json').historial, fuente.id),
		// los que no son de un cuadro (p. ej. la serie nacional de matrícula) se siguen listando uno por uno
		indicadores: indicadores.filter((i) => !i.cuadro),
		totalIndicadores: indicadores.length,
		cuadros,
		territoriosPorNivel
	};
};
