import type { EntradaIndice } from '#lib/datos.ts';
import { leerDatos, minimo } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = () => {
	const indice = leerDatos<EntradaIndice[]>('territorios_index.json');
	const porDepto = (nivel: string) =>
		indice.reduce<Record<string, number>>((c, t) => {
			if (t.nivel === nivel) c[t.depto] = (c[t.depto] ?? 0) + 1;
			return c;
		}, {});
	return {
		pais: indice.filter((t) => t.nivel === 'pais').map(minimo),
		departamentos: indice.filter((t) => t.nivel === 'departamento').map(minimo),
		secciones: porDepto('seccion'),
		segmentos: porDepto('segmento'),
		localidades: porDepto('localidad'),
		montevideo: indice
			.filter((t) => t.nivel === 'municipio_mvd' || t.nivel === 'barrio_mvd' || t.nivel === 'ccz_mvd')
			.map(minimo)
	};
};
