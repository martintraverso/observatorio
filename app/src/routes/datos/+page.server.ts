import type { Fuente } from '#lib/datos.ts';
import { leerDatos } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

export interface Descarga {
	nombre: string;
	grupo: string;
	descripcion: string;
	bytes: number;
	sha256: string;
}

export const load: PageServerLoad = () => ({
	...leerDatos<{ generado: string; licencia: string; cita: string; archivos: Descarga[] }>('descargas.json'),
	// AC-V30: la licencia de cada fuente activa
	fuentes: leerDatos<Fuente[]>('fuentes.json')
		.filter((f) => f.estado === 'activa')
		.map((f) => ({ id: f.id, nombre: f.nombre, organismo: f.organismo, licencia: f.licencia }))
});
