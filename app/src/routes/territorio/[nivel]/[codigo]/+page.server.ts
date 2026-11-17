// Lista de territorios a prerenderizar: uno por entrada del índice (AC-G3, AC-F1).
// Corre solo en el build; los datos los lee +page.ts.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { EntryGenerator } from './$types';

export const entries: EntryGenerator = () => {
	const indice = JSON.parse(
		readFileSync(resolve('static/datos-web/territorios_index.json'), 'utf-8')
	) as { nivel: string; codigo: string }[];
	return indice.map(({ nivel, codigo }) => ({ nivel, codigo }));
};
