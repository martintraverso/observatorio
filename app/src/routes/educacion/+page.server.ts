import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { CARPETA_DATOS } from '#lib/datos.ts';
import { leerDatos } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

/** Un cuadro del anuario del MEC con datos (pipeline/web.py → educacion_catalogo.json, AC-E32). */
export interface CuadroCatalogo {
	cuadro: string;
	titulo: string;
	tipo: string;
	anios: string[];
	/** Una tasa calculada del cuadro, para abrirlo en el mapa; null si no tiene. */
	mapa: string | null;
}

// F4.8a3 (#226): sin el archivo (datos anteriores) o sin la fuente activa, la página dice que no hay cuadros.
export const load: PageServerLoad = () => ({
	cuadros: existsSync(resolve('static', CARPETA_DATOS, 'educacion_catalogo.json'))
		? leerDatos<CuadroCatalogo[]>('educacion_catalogo.json')
		: []
});
