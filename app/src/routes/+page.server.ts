import type { EntradaIndice } from '#lib/datos.ts';
import { leerDatos, minimo } from '#lib/server/datos-build.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = () => {
	const indice = leerDatos<EntradaIndice[]>('territorios_index.json');
	return {
		departamentos: indice.filter((t) => t.nivel === 'departamento').map(minimo),
		conteo: indice.reduce<Record<string, number>>((c, t) => ((c[t.nivel] = (c[t.nivel] ?? 0) + 1), c), {})
	};
};
