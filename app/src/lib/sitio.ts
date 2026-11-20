// Datos del sitio que no salen del pipeline.

/** Repositorio de GitHub (usuario/repo). En Actions viene de GITHUB_REPOSITORY. */
export const REPOSITORIO: string = import.meta.env.VITE_REPOSITORIO || 'martintraverso/observatorio';
export const URL_REPOSITORIO = `https://github.com/${REPOSITORIO}`;

/** Descarga estable de un archivo del último release de datos. */
export function urlDescarga(archivo: string): string {
	return `${URL_REPOSITORIO}/releases/latest/download/${archivo}`;
}

export const NOMBRE_SITIO = 'Observatorio Uruguay';

export const NAVEGACION = [
	{ ruta: '/', texto: 'Mapa' },
	{ ruta: '/fichas', texto: 'Fichas' },
	{ ruta: '/datos', texto: 'Datos' },
	{ ruta: '/fuentes', texto: 'Fuentes' }
] as const;
