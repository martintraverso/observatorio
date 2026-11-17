import { error } from '@sveltejs/kit';
import { cargarFicha, ErrorDatos, esNivel } from '#lib/datos.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, fetch }) => {
	if (!esNivel(params.nivel)) error(404, `No existe el nivel territorial «${params.nivel}».`);
	try {
		return { ficha: await cargarFicha(params.nivel, params.codigo, fetch) };
	} catch (e) {
		if (e instanceof ErrorDatos && e.status === 404) {
			error(404, `No hay un territorio con código ${params.codigo} en el nivel ${params.nivel}.`);
		}
		throw e;
	}
};
