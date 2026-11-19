import type { Fuente } from '#lib/datos.ts';
import { datosCatalogo, type CapturaHistorial } from '#lib/fuentes.ts';
import { leerDatos } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

// Sin el historial completo: solo lo que la página muestra (#96, AC-G6).
export const load: PageServerLoad = () => {
	const fuentes = leerDatos<Fuente[]>('fuentes.json');
	const { historial } = leerDatos<{ historial: CapturaHistorial[] }>('capturas.json');
	return { fuentes, ...datosCatalogo(fuentes, historial) };
};
