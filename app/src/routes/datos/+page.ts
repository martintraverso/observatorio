import { cargarManifest } from '#lib/datos.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({ manifest: await cargarManifest(fetch) });
