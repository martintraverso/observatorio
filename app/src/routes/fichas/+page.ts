import { cargarIndice } from '#lib/datos.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	const indice = await cargarIndice(fetch);
	const departamentos = indice.filter((t) => t.nivel === 'departamento');
	const porDepto = (nivel: string) =>
		indice.reduce<Record<string, number>>((c, t) => {
			if (t.nivel === nivel) c[t.depto] = (c[t.depto] ?? 0) + 1;
			return c;
		}, {});
	return {
		departamentos,
		secciones: porDepto('seccion'),
		segmentos: porDepto('segmento'),
		localidades: porDepto('localidad'),
		montevideo: indice.filter((t) => t.nivel === 'barrio_mvd' || t.nivel === 'ccz_mvd')
	};
};
