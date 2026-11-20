// Catálogo de fuentes (M8, AC-SRC1…SRC3): resumen, filtros y capturas.

import { etiquetaNivel, type Fuente, type Nivel } from './datos.ts';

export interface CapturaHistorial {
	id: string;
	fuente_id: string;
	archivo: string;
	sha256: string;
	fecha_proceso: string;
	resultado: 'nuevo' | 'reprocesado' | 'sin cambios' | 'error';
	detalle: string | null;
}

export const ESTADOS = ['activa', 'en preparación', 'a relevar'] as const;

export interface Filtros {
	texto: string;
	organismo: string;
	nivel: string;
	estado: string;
}

export const SIN_FILTROS: Filtros = { texto: '', organismo: '', nivel: '', estado: '' };

function plegar(s: string): string {
	return s.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
}

/** AC-SRC2: los filtros se combinan (todos tienen que cumplirse). */
export function filtrar(fuentes: Fuente[], f: Filtros): Fuente[] {
	const q = plegar(f.texto.trim());
	return fuentes.filter(
		(x) =>
			(!q || plegar(`${x.nombre} ${x.organismo} ${x.temas.join(' ')}`).includes(q)) &&
			(!f.organismo || x.organismo === f.organismo) &&
			(!f.nivel || x.niveles_publicados.includes(f.nivel as Nivel)) &&
			(!f.estado || x.estado === f.estado)
	);
}

/** Corridas de una fuente, de la más nueva a la más vieja. */
export function historialDe(historial: CapturaHistorial[], fuenteId: string): CapturaHistorial[] {
	return historial.filter((c) => c.fuente_id === fuenteId).sort((a, b) => b.fecha_proceso.localeCompare(a.fecha_proceso));
}

/** Última captura procesada con éxito (nuevo o reprocesado). */
export function ultimaCaptura(historial: CapturaHistorial[], fuenteId: string): CapturaHistorial | null {
	return historialDe(historial, fuenteId).find((c) => c.resultado === 'nuevo' || c.resultado === 'reprocesado') ?? null;
}

export function resumen(fuentes: Fuente[], historial: CapturaHistorial[]) {
	const porEstado = Object.fromEntries(ESTADOS.map((e) => [e, fuentes.filter((f) => f.estado === e).length])) as Record<
		(typeof ESTADOS)[number],
		number
	>;
	const ultimaRevision = historial.map((c) => c.fecha_proceso).sort().at(-1) ?? null;
	return { porEstado, ultimaRevision };
}

/**
 * Lo que la página /fuentes necesita del historial, calculado en el build: el resumen y la fecha de la
 * última captura de cada fuente. El historial completo no se incrusta en la página porque crece en cada
 * corrida de datos (#96, AC-G6); está en /fuentes/<id>.
 */
export function datosCatalogo(fuentes: Fuente[], historial: CapturaHistorial[]) {
	return {
		resumen: resumen(fuentes, historial),
		ultimas: Object.fromEntries(fuentes.map((f) => [f.id, ultimaCaptura(historial, f.id)?.fecha_proceso ?? null])) as Record<
			string,
			string | null
		>
	};
}

export const TEXTO_RESULTADO: Record<CapturaHistorial['resultado'], string> = {
	nuevo: 'Nuevo',
	reprocesado: 'Reprocesado',
	'sin cambios': 'Sin cambios',
	error: 'Error'
};

/** Qué tan fino es cada nivel (para comparar). Los de Montevideo cubren solo ese departamento. */
const FINURA: Record<string, number> = {
	pais: 0,
	departamento: 1,
	municipio_mvd: 2,
	ccz_mvd: 2,
	seccion: 3,
	barrio_mvd: 3,
	localidad: 3,
	segmento: 4
};
const SOLO_MONTEVIDEO = ['municipio_mvd', 'ccz_mvd', 'barrio_mvd'];

/**
 * AC-V28: «Nivel más detallado» de una fuente, sin engañar: el nivel más fino con alcance en todo el país y,
 * si hay uno de Montevideo más fino, también ese («Departamento · Municipio (solo Montevideo)»).
 */
export function nivelesDetallados(f: Pick<Fuente, 'niveles_publicados'>): string {
	const niveles = f.niveles_publicados as string[];
	const finura = (n: string) => FINURA[n] ?? 0;
	const nacionales = niveles.filter((n) => !SOLO_MONTEVIDEO.includes(n));
	const nacional = nacionales.reduce<string | null>((a, n) => (a === null || finura(n) > finura(a) ? n : a), null);
	const montevideo = niveles
		.filter((n) => SOLO_MONTEVIDEO.includes(n) && (nacional === null || finura(n) > finura(nacional)))
		.map((n) => `${etiquetaNivel(n).replace(' (Montevideo)', '')} (solo Montevideo)`);
	return [...(nacional ? [etiquetaNivel(nacional)] : []), ...montevideo].join(' · ');
}
