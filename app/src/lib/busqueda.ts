// Búsqueda de territorios sobre territorios_index.json (M5, AC-S1…S3). Funciones puras, sin DOM.

import type { EntradaIndice, Nivel } from './datos.ts';

/** Igual que pipeline/web.py `plegar`: minúsculas, sin tildes, espacios simples. */
export function plegar(texto: string): string {
	return texto
		.normalize('NFKD')
		.replace(/\p{M}/gu, '')
		.toLowerCase()
		.split(/\s+/)
		.filter(Boolean)
		.join(' ');
}

/** Largo del código INE -> nivel (AC-S2). */
export const NIVEL_POR_LARGO: Record<number, Nivel> = {
	2: 'departamento',
	4: 'seccion',
	5: 'localidad',
	7: 'segmento'
};

/** Niveles que se buscan por nombre; secciones y segmentos solo por código ("Sección 05" se repite). */
const POR_NOMBRE = new Set<Nivel>(['departamento', 'region', 'localidad', 'barrio_mvd', 'ccz_mvd']);

/** Orden de los niveles cuando empatan. */
const ORDEN_NIVEL: Nivel[] = ['departamento', 'region', 'localidad', 'barrio_mvd', 'ccz_mvd', 'seccion', 'segmento', 'area_especial'];

export interface Resultado {
	t: EntradaIndice;
	/** Menor es mejor: 0 código exacto, 1 nombre exacto, 2 empieza igual, 3 una palabra empieza igual, 4 contiene, 5 código que empieza igual. */
	puntaje: number;
	/** Nivel y padre para mostrar: "Sección 05 · San José". */
	contexto: string;
}

export interface Buscador {
	buscar(consulta: string, limite?: number): Resultado[];
	/** Si la consulta es un código INE válido de un territorio existente, ese territorio (AC-S2). */
	porCodigo(consulta: string): EntradaIndice | null;
}

const ETIQUETA: Record<Nivel, string> = {
	pais: 'País',
	departamento: 'Departamento',
	seccion: 'Sección censal',
	segmento: 'Segmento censal',
	localidad: 'Localidad',
	barrio_mvd: 'Barrio',
	municipio_mvd: 'Municipio',
	ccz_mvd: 'CCZ',
	area_especial: 'Área especial',
	region: 'Región'
};

export function crearBuscador(indice: EntradaIndice[]): Buscador {
	const porId = new Map(indice.map((t) => [t.id, t]));
	const porNivelCodigo = new Map(indice.map((t) => [`${t.nivel}/${t.codigo}`, t]));

	function contexto(t: EntradaIndice): string {
		const padres: string[] = [];
		let p = t.padre_id ? porId.get(t.padre_id) : undefined;
		while (p) {
			padres.push(p.nombre);
			p = p.padre_id ? porId.get(p.padre_id) : undefined;
		}
		return [ETIQUETA[t.nivel], ...padres].join(' · ');
	}

	function porCodigo(consulta: string): EntradaIndice | null {
		const c = consulta.trim();
		const nivel = /^\d+$/.test(c) ? NIVEL_POR_LARGO[c.length] : undefined;
		return nivel ? (porNivelCodigo.get(`${nivel}/${c}`) ?? null) : null;
	}

	function puntuar(t: EntradaIndice, q: string, esNumero: boolean): number | null {
		if (esNumero) {
			if (t.codigo === q) return 0;
			if (t.codigo.startsWith(q) && t.nivel !== 'area_especial') return 5;
			return null;
		}
		if (!POR_NOMBRE.has(t.nivel)) return null;
		const n = t.nombre_busqueda;
		if (n === q) return 1;
		if (n.startsWith(q)) return 2;
		if (n.split(/[\s,.()-]+/).some((p) => p.startsWith(q))) return 3;
		if (n.includes(q)) return 4;
		return null;
	}

	function buscar(consulta: string, limite = 10): Resultado[] {
		const q = plegar(consulta);
		if (q.length < 2) return [];
		const esNumero = /^\d+$/.test(q);
		const encontrados: Resultado[] = [];
		for (const t of indice) {
			const puntaje = puntuar(t, q, esNumero);
			if (puntaje !== null) encontrados.push({ t, puntaje, contexto: '' });
		}
		encontrados.sort(
			(a, b) =>
				a.puntaje - b.puntaje ||
				ORDEN_NIVEL.indexOf(a.t.nivel) - ORDEN_NIVEL.indexOf(b.t.nivel) ||
				a.t.codigo.length - b.t.codigo.length ||
				a.t.nombre.localeCompare(b.t.nombre, 'es') ||
				a.t.codigo.localeCompare(b.t.codigo)
		);
		return encontrados.slice(0, limite).map((r) => ({ ...r, contexto: contexto(r.t) }));
	}

	return { buscar, porCodigo };
}
