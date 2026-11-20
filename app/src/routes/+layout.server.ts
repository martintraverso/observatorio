// Fuentes activas para el pie de página (AC-V29): se leen en el build, como el resto de los datos.
import type { Fuente } from '#lib/datos.ts';
import { leerDatos } from '#lib/server/datos-build.ts';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = () => ({
	fuentesActivas: leerDatos<Fuente[]>('fuentes.json')
		.filter((f) => f.estado === 'activa')
		.map((f) => ({ id: f.id, nombre: f.nombre, organismo: f.organismo }))
});
