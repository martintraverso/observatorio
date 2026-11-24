import { error } from '@sveltejs/kit';
import { cargarFicha, ErrorDatos, esNivel, leerJson } from '#lib/datos.ts';
import { zoomMinimo, type NivelCatalogo } from '#lib/mapa/estado.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, fetch }) => {
	if (!esNivel(params.nivel)) error(404, `No existe el nivel territorial «${params.nivel}».`);
	try {
		const ficha = await cargarFicha(params.nivel, params.codigo, fetch);
		// F2.8c: si la ficha trae series (p. ej. la ECH), el total del país tal como lo publica la fuente.
		const conSeries = ficha.nivel !== 'pais' && ficha.observaciones.some((o) => o.tipo_periodo !== 'censo');
		const pais = conSeries ? await cargarFicha('pais', 'UY', fetch).catch(() => null) : null;
		// M11.2: el zoom desde el que el nivel está en el PMTiles, del catálogo (lo usa el localizador de cerca).
		const catalogo = await leerJson<NivelCatalogo[]>('niveles.json', fetch).catch(() => []);
		return { ficha, pais, minzoom: zoomMinimo(catalogo, ficha.nivel) };
	} catch (e) {
		if (e instanceof ErrorDatos && e.status === 404) {
			error(404, `No hay un territorio con código ${params.codigo} en el nivel ${params.nivel}.`);
		}
		throw e;
	}
};
