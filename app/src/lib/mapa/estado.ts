// Lógica del mapa sin DOM (M6): temas, disponibilidad por nivel, clases de la coropleta y estado en la URL.

import type { Indicador, Nivel } from '../datos.ts';
import { numero } from '../formato.ts';

/** Temas de la app, en orden (SYSTEM.md §8). */
export const TEMAS = ['Población', 'Vivienda', 'Hogares', 'Trabajo', 'Ingresos', 'Educación'] as const;
export type Tema = (typeof TEMAS)[number];

/** Niveles que se pueden pintar en el mapa, de menos a más detallado. */
export const NIVELES_MAPA = ['departamento', 'seccion', 'segmento'] as const satisfies readonly Nivel[];
export type NivelMapa = (typeof NIVELES_MAPA)[number];

export const ETIQUETA_NIVEL_MAPA: Record<NivelMapa, string> = {
	departamento: 'Departamento',
	seccion: 'Sección',
	segmento: 'Segmento'
};

/** Desde qué zoom aparecen los segmentos en el PMTiles (pipeline/web.py PMTILES_MINZOOM). */
export const ZOOM_SEGMENTOS = 9;

/** Lo que trae indicadores.json para cada indicador. */
export interface IndicadorMapa extends Indicador {
	tema: string;
	niveles: Nivel[];
	periodos: string[];
}

export function indicadoresDelTema(indicadores: IndicadorMapa[], tema: string): IndicadorMapa[] {
	return indicadores.filter((i) => i.tema === tema);
}

/** El nivel más detallado del mapa en que el indicador tiene datos, o null. */
export function nivelMasDetallado(ind: IndicadorMapa): NivelMapa | null {
	for (let i = NIVELES_MAPA.length - 1; i >= 0; i--) {
		if (ind.niveles.includes(NIVELES_MAPA[i])) return NIVELES_MAPA[i];
	}
	return null;
}

/**
 * AC-M2: si el indicador no se publica en el nivel elegido, un aviso que nombra el nivel más
 * detallado disponible. Nunca se pinta un valor inventado ni se sustituye en silencio.
 */
export function avisoNivel(ind: IndicadorMapa, nivel: NivelMapa): { mensaje: string; alternativa: NivelMapa | null } | null {
	if (ind.niveles.includes(nivel)) return null;
	const alternativa = nivelMasDetallado(ind);
	const donde = ETIQUETA_NIVEL_MAPA[nivel].toLowerCase();
	return {
		mensaje: alternativa
			? `«${ind.nombre}» no se publica por ${donde}. El nivel más detallado con datos es ${ETIQUETA_NIVEL_MAPA[alternativa].toLowerCase()}.`
			: `«${ind.nombre}» no se publica por ${donde} ni en otro nivel del mapa.`,
		alternativa
	};
}

// ---------------------------------------------------------------- clases (cuantiles)

export interface Clases {
	/** Límites superiores de cada clase salvo la última (n-1 cortes para n clases). */
	cortes: number[];
	min: number;
	max: number;
}

/** Hasta `n` clases por cuantiles; menos si hay pocos valores distintos. */
export function clasesCuantiles(valores: number[], n = 5): Clases | null {
	const v = valores.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
	if (!v.length) return null;
	const cortes: number[] = [];
	for (let k = 1; k < n; k++) {
		const c = v[Math.min(v.length - 1, Math.floor((k * v.length) / n))];
		if (c > (cortes.at(-1) ?? -Infinity) && c < v.at(-1)!) cortes.push(c);
	}
	return { cortes, min: v[0], max: v.at(-1)! };
}

/** Índice de clase (0..cortes.length) de un valor. */
export function clase(valor: number, c: Clases): number {
	let i = 0;
	while (i < c.cortes.length && valor > c.cortes[i]) i++;
	return i;
}

/** Etiquetas de la leyenda en es-UY: "Hasta 1.234", "1.235 a 5.000", "Más de 5.000". */
export function etiquetasLeyenda(c: Clases): string[] {
	if (!c.cortes.length) return [c.min === c.max ? numero(c.min) : `${numero(c.min)} a ${numero(c.max)}`];
	return [
		`Hasta ${numero(c.cortes[0])}`,
		...c.cortes.slice(1).map((corte, i) => `${numero(c.cortes[i] + 1)} a ${numero(corte)}`),
		`Más de ${numero(c.cortes.at(-1)!)}`
	];
}

// ---------------------------------------------------------------- estado en la URL (AC-M5)

export interface EstadoMapa {
	indicador: string;
	nivel: NivelMapa;
	periodo: string;
	/** Territorio seleccionado: "seccion/1605", o null. */
	territorio: string | null;
}

export function estadoDesdeUrl(params: URLSearchParams, indicadores: IndicadorMapa[]): EstadoMapa {
	const ind = indicadores.find((i) => i.codigo === params.get('indicador')) ?? indicadores[0];
	const nivel = (NIVELES_MAPA as readonly string[]).includes(params.get('nivel') ?? '')
		? (params.get('nivel') as NivelMapa)
		: 'departamento';
	const periodo = ind?.periodos.includes(params.get('periodo') ?? '') ? params.get('periodo')! : (ind?.periodos.at(-1) ?? '');
	const t = params.get('territorio');
	const territorio = t && /^[a-z_]+\/[0-9A-Za-z-]+$/.test(t) ? t : null;
	return { indicador: ind?.codigo ?? '', nivel, periodo, territorio };
}

export function urlDesdeEstado(e: EstadoMapa): string {
	const p = new URLSearchParams({ indicador: e.indicador, nivel: e.nivel, periodo: e.periodo });
	if (e.territorio) p.set('territorio', e.territorio);
	return `?${p.toString()}`;
}
