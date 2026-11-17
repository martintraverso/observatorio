// Lectura de datos durante el build (solo en el servidor de prerender).
//
// Las páginas que resumen archivos grandes (índice de 1,25 MB, manifest de 0,7 MB) los leen acá,
// en +page.server.ts, y devuelven solo lo que muestran. Si los leyeran con fetch en +page.ts,
// SvelteKit incrustaría el archivo entero en el HTML de la página.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { CARPETA_DATOS } from '#lib/datos.ts';

export function leerDatos<T>(ruta: string): T {
	return JSON.parse(readFileSync(resolve('static', CARPETA_DATOS, ruta), 'utf-8')) as T;
}

/** Lo mínimo de un territorio para listarlo y enlazarlo. */
export function minimo<T extends { id: string; nivel: string; codigo: string; nombre: string }>(
	t: T
): Pick<T, 'id' | 'nivel' | 'codigo' | 'nombre'> {
	return { id: t.id, nivel: t.nivel, codigo: t.codigo, nombre: t.nombre };
}
