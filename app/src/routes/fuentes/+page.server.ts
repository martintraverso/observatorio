import type { Fuente } from '#lib/datos.ts';
import { leerDatos } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = () => ({ fuentes: leerDatos<Fuente[]>('fuentes.json') });
