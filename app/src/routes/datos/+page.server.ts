import type { Manifest } from '#lib/datos.ts';
import { leerDatos } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = () => {
	const manifest = leerDatos<Manifest>('manifest.json');
	return { generado: manifest.generado, archivos: manifest.archivos.length };
};
