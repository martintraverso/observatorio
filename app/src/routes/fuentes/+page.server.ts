import type { Fuente } from '#lib/datos.ts';
import type { CapturaHistorial } from '#lib/fuentes.ts';
import { leerDatos } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = () => ({
	fuentes: leerDatos<Fuente[]>('fuentes.json'),
	historial: leerDatos<{ historial: CapturaHistorial[] }>('capturas.json').historial
});
