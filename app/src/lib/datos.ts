// Acceso a los datos publicados por el pipeline (pipeline/web.py).
//
// Un solo lugar define de dónde salen: la carpeta `datos-web/` dentro del sitio
// (static/datos-web en desarrollo, copiada desde web.zip del último release en el deploy).
// La app no necesita servidor: todo son archivos JSON estáticos.

import { asset, resolve } from '$app/paths';

/** Carpeta de los datos dentro del sitio. */
export const CARPETA_DATOS = 'datos-web';

// ---------------------------------------------------------------- tipos (ver pipeline/web.py)

export type Nivel =
	| 'departamento'
	| 'seccion'
	| 'segmento'
	| 'localidad'
	| 'barrio_mvd'
	| 'ccz_mvd'
	| 'area_especial';

export interface EntradaIndice {
	id: string;
	nivel: Nivel;
	codigo: string;
	nombre: string;
	nombre_busqueda: string;
	depto: string;
	padre_id: string | null;
	bbox: [number, number, number, number];
}

export interface Observacion {
	indicador: string;
	periodo: string;
	valor: number | null;
	es_estimado: boolean;
	captura_id: string;
}

export interface Resumen {
	id: string;
	nivel: Nivel;
	codigo: string;
	nombre: string;
	valores: Record<string, Record<string, number | null>>;
	estimados?: string[];
}

export interface Relacion {
	tipo: string;
	destino_id: string;
	metodo: string;
	nivel: string;
	codigo: string;
	nombre: string | null;
	existe: boolean;
}

export interface Indicador {
	codigo: string;
	nombre: string;
	unidad: string;
	columna_origen: string;
	fuente_id: string;
	nota: string;
}

export interface Captura {
	id: string;
	fuente_id: string;
	archivo: string;
	sha256: string;
	fecha_proceso: string;
}

export interface FuenteRef {
	nombre: string;
	organismo: string;
	licencia: string;
	pagina: string;
	url_descarga: string;
}

export interface Ficha {
	id: string;
	nivel: Nivel;
	codigo: string;
	nombre: string;
	depto: string;
	version_geo: string;
	area_km2: number | null;
	codigo_iso: string | null;
	bbox: [number, number, number, number];
	padres: Resumen[];
	contenidos: Partial<Record<Nivel, Resumen[]>>;
	relaciones: Relacion[];
	observaciones: Observacion[];
	indicadores: Record<string, Indicador>;
	capturas: Record<string, Captura>;
	fuentes: Record<string, FuenteRef>;
}

export interface Fuente extends FuenteRef {
	id: string;
	formato: string;
	frecuencia: string;
	estado: 'activa' | 'en preparación' | 'a relevar';
	contacto: string | null;
	version_geo: string | null;
	temas: string[];
	nivel_mas_detallado: Nivel;
	niveles_publicados: Nivel[];
	notas: string[];
}

export interface ArchivoManifest {
	ruta: string;
	bytes: number;
	sha256: string;
}

export interface Manifest {
	generado: string;
	capturas: string[];
	archivos: ArchivoManifest[];
}

// ---------------------------------------------------------------- etiquetas

export const NOMBRE_NIVEL: Record<Nivel, string> = {
	departamento: 'Departamento',
	seccion: 'Sección censal',
	segmento: 'Segmento censal',
	localidad: 'Localidad censal',
	barrio_mvd: 'Barrio (Montevideo)',
	ccz_mvd: 'CCZ (Montevideo)',
	area_especial: 'Área especial'
};

export const NIVELES: Nivel[] = Object.keys(NOMBRE_NIVEL) as Nivel[];

export function esNivel(x: string): x is Nivel {
	return x in NOMBRE_NIVEL;
}

// ---------------------------------------------------------------- carga

type Fetch = typeof fetch;

/** URL de un archivo de datos, con el base path del sitio (p. ej. /observatorio/datos/...). */
export function urlDatos(ruta: string): string {
	return asset(`/${CARPETA_DATOS}/${ruta}` as Parameters<typeof asset>[0]);
}

const cache = new Map<string, Promise<unknown>>();

/**
 * Lee un JSON de datos. Usar el `fetch` que SvelteKit pasa a `load` (sirve durante el prerender
 * y evita pedir dos veces lo mismo al hidratar). Cachea por ruta en el navegador.
 */
export function leerJson<T>(ruta: string, f: Fetch = fetch): Promise<T> {
	const enNavegador = typeof window !== 'undefined';
	if (enNavegador && cache.has(ruta)) return cache.get(ruta) as Promise<T>;
	const p = f(urlDatos(ruta)).then((r) => {
		if (!r.ok) throw new ErrorDatos(ruta, r.status);
		return r.json() as Promise<T>;
	});
	if (enNavegador) {
		cache.set(ruta, p);
		p.catch(() => cache.delete(ruta));
	}
	return p;
}

export class ErrorDatos extends Error {
	constructor(
		public ruta: string,
		public status: number
	) {
		super(`No se pudo leer ${ruta} (HTTP ${status})`);
	}
}

export const cargarManifest = (f?: Fetch) => leerJson<Manifest>('manifest.json', f);
export const cargarIndice = (f?: Fetch) => leerJson<EntradaIndice[]>('territorios_index.json', f);
export const cargarFuentes = (f?: Fetch) => leerJson<Fuente[]>('fuentes.json', f);
export const cargarIndicadores = (f?: Fetch) => leerJson<Indicador[]>('indicadores.json', f);
export const cargarFicha = (nivel: Nivel, codigo: string, f?: Fetch) =>
	leerJson<Ficha>(`fichas/${nivel}/${encodeURIComponent(codigo)}.json`, f);

// ---------------------------------------------------------------- utilidades

/** Ruta de la ficha de un territorio (sin base path: usar con resolve()). */
export function rutaFicha(t: { nivel: string; codigo: string }): `/territorio/${string}/${string}` {
	return `/territorio/${t.nivel}/${t.codigo}`;
}

/** "INE-2023/seccion/0701" -> { nivel: "seccion", codigo: "0701" }. */
export function partesId(id: string): { nivel: string; codigo: string } {
	const [, nivel, codigo] = id.split('/');
	return { nivel, codigo };
}

/** href de la ficha de un territorio, con el base path del sitio. */
export function hrefFicha(t: { nivel: string; codigo: string }): string {
	return resolve('/territorio/[nivel]/[codigo]', { nivel: t.nivel, codigo: t.codigo });
}
