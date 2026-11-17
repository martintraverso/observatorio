import { cargarFuentes } from '#lib/datos.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({ fuentes: await cargarFuentes(fetch) });
