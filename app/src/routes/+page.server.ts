import type { Fuente } from '#lib/datos.ts';
import type { IndicadorMapa, NivelCatalogo } from '#lib/mapa/estado.ts';
import { leerDatos } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

// Departamentos con su caja, para encuadrar el mapa al cambiar de nivel (AC-V7). ~2 KB.
type EntradaIndice = { nivel: string; codigo: string; nombre: string; bbox: [number, number, number, number] };

const SIN_USO_EN_EL_MAPA = new Set(['formula', 'nota', 'columna_origen', 'cuadro', 'corte']);

/**
 * AC-V41 (#249): cuántos indicadores de cada tema y nivel educativo («Educación|Primaria», «Vivienda|») no van al
 * mapa (`mapa: false`, AC-V33). La lista dice que hay más y adónde ir; nunca los lista.
 */
function fueraDelMapa(indicadores: IndicadorMapa[]): Record<string, number> {
	const n: Record<string, number> = {};
	for (const i of indicadores) if (i.mapa === false) n[`${i.tema}|${i.grupo ?? ''}`] = (n[`${i.tema}|${i.grupo ?? ''}`] ?? 0) + 1;
	return n;
}

export const load: PageServerLoad = () => ({
	departamentos: leerDatos<EntradaIndice[]>('territorios_index.json')
		.filter((t) => t.nivel === 'departamento')
		.map(({ codigo, nombre, bbox }) => ({ codigo, nombre, bbox }))
		.sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')),
	// #214: solo los indicadores que van a la lista del mapa (de educación, las tasas calculadas; #213), y sin los campos
	// que el mapa no lee (fórmula, nota, columna de origen…): con la educación activa pesaban 80 KB de la página (AC-G6, #222)
	indicadores: leerDatos<IndicadorMapa[]>('indicadores.json')
		.filter((i) => i.mapa !== false)
		.map((i) => Object.fromEntries(Object.entries(i).filter(([k]) => !SIN_USO_EN_EL_MAPA.has(k))) as IndicadorMapa),
	// M11.2: catálogo de niveles del pipeline (niveles.json, AC-N1): etiquetas, orden, zoom mínimo y ámbito.
	fueraDelMapa: fueraDelMapa(leerDatos<IndicadorMapa[]>('indicadores.json')),
	catalogo: leerDatos<NivelCatalogo[]>('niveles.json'),
	fuentes: leerDatos<Fuente[]>('fuentes.json').map((f) => ({ id: f.id, nombre: f.nombre, organismo: f.organismo }))
});
