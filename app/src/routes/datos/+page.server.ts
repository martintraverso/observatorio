import { leerDatos } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

export interface Descarga {
	nombre: string;
	grupo: string;
	descripcion: string;
	bytes: number;
	sha256: string;
}

export const load: PageServerLoad = () =>
	leerDatos<{ generado: string; licencia: string; cita: string; archivos: Descarga[] }>('descargas.json');
