import { cargarIndice } from '#lib/datos.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	const indice = await cargarIndice(fetch);
	return {
		departamentos: indice.filter((t) => t.nivel === 'departamento'),
		conteo: indice.reduce<Record<string, number>>((c, t) => ((c[t.nivel] = (c[t.nivel] ?? 0) + 1), c), {})
	};
};
