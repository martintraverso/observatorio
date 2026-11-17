import { error } from '@sveltejs/kit';
import type { EntradaIndice, Fuente } from '#lib/datos.ts';
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
	return {
		fuente,
		historial: historialDe(leerDatos<{ historial: CapturaHistorial[] }>('capturas.json').historial, fuente.id),
		indicadores: leerDatos<IndicadorMapa[]>('indicadores.json').filter((i) => i.fuente_id === fuente.id),
		territoriosPorNivel
	};
};
