import type { Fuente } from '#lib/datos.ts';
import type { IndicadorMapa } from '#lib/mapa/estado.ts';
import { leerDatos } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = () => ({
	indicadores: leerDatos<IndicadorMapa[]>('indicadores.json'),
	fuentes: leerDatos<Fuente[]>('fuentes.json').map((f) => ({ id: f.id, nombre: f.nombre, organismo: f.organismo }))
});
