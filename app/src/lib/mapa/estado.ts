// Lógica del mapa sin DOM (M6): temas, niveles según el catálogo (M11), clases de la coropleta y estado en la URL.

import type { Indicador } from '../datos.ts';
import { numero } from '../formato.ts';

/** Temas de la app, en orden (SYSTEM.md §8). */
export const TEMAS = ['Población', 'Vivienda', 'Hogares', 'Trabajo', 'Ingresos', 'Educación'] as const;
export type Tema = (typeof TEMAS)[number];

/** Un nivel del catálogo que escribe el pipeline en niveles.json (M11.1, AC-N1). */
export interface NivelCatalogo {
	id: string;
	etiqueta: string;
	/** Aclaración bajo la etiqueta en el selector, p. ej. «Solo Montevideo» (AC-V2). */
	ayuda: string | null;
	/** De grueso a fino (D2). */
	orden: number;
	/** Va al mapa (D1) y tiene capa en el PMTiles. */
	dibujable: boolean;
	/** Tiene capa en el PMTiles, vaya o no al selector (el mapa resalta ahí lo elegido en la búsqueda). */
	capa: boolean;
	/** Zoom desde el que la capa está en el PMTiles; null = desde el principio. */
	minzoom: number | null;
	/** Dónde tiene sentido encuadrar el nivel (AC-V7). */
	ambito: 'pais' | 'montevideo';
	/** Niveles que contienen enteros a sus territorios (AC-N7, #202). */
	dentro_de: string[];
}

/** Un nivel del mapa: cualquier id del catálogo (M11.2: la app no tiene una lista fija, AC-N13). */
export type NivelMapa = string;

/** Los niveles que se pueden dibujar, en el orden del catálogo (capas del mapa). */
export function nivelesDibujables(catalogo: NivelCatalogo[]): NivelCatalogo[] {
	return catalogo.filter((n) => n.dibujable).sort((a, b) => a.orden - b.orden);
}

/** AC-N4: los niveles que ofrece el selector para un indicador: con datos y dibujables, en el orden del catálogo. */
export function nivelesOfrecidos(
	ind: { niveles: string[]; niveles_mapa?: string[] } | undefined,
	catalogo: NivelCatalogo[]
): NivelMapa[] {
	if (!ind) return [];
	// AC-N6 (#204): los niveles con valor en al menos 2 territorios (`niveles_mapa`, del pipeline); sin ese dato, los
	// niveles con datos.
	const conDatos = ind.niveles_mapa ?? ind.niveles;
	return nivelesDibujables(catalogo)
		.filter((n) => conDatos.includes(n.id))
		.map((n) => n.id);
}

/**
 * AC-N7: el nivel al cambiar de tema o indicador. Se conserva si se ofrece; si no, el más cercano de los niveles que
 * lo contienen (`dentro_de`, decisión del mantenedor en #202: de un barrio no se pasa a la seccional, que no lo
 * contiene); si ninguno se ofrece, el más grueso ofrecido. null si no se ofrece ninguno (solo país y región).
 */
export function nivelAlCambiar(actual: NivelMapa, ofrecidos: NivelMapa[], catalogo: NivelCatalogo[]): NivelMapa | null {
	if (!ofrecidos.length) return null;
	if (ofrecidos.includes(actual)) return actual;
	const orden = (id: string) => catalogo.find((n) => n.id === id)?.orden ?? Infinity;
	const contienen = catalogo.find((n) => n.id === actual)?.dentro_de ?? [];
	const padre = ofrecidos.filter((id) => contienen.includes(id)).sort((a, b) => orden(b) - orden(a))[0];
	return padre ?? [...ofrecidos].sort((a, b) => orden(a) - orden(b))[0];
}

/**
 * AC-V7 (M11.3): dónde se encuadra el mapa al elegir un nivel, según el catálogo y sin código por nivel:
 * los niveles solo de Montevideo, en Montevideo; los que no están dentro de un departamento (el departamento mismo),
 * en el país; los demás, en el departamento elegido (con el zoom mínimo del nivel, si tiene).
 */
export function encuadreNivel(catalogo: NivelCatalogo[], nivel: string): 'montevideo' | 'pais' | 'departamento' {
	const n = catalogo.find((c) => c.id === nivel);
	if (n?.ambito === 'montevideo') return 'montevideo';
	return n?.dentro_de.includes('departamento') ? 'departamento' : 'pais';
}

/** Zoom desde el que se dibuja el nivel (0 si no tiene mínimo). Reemplaza la constante de los segmentos. */
export function zoomMinimo(catalogo: NivelCatalogo[], nivel: string): number {
	return catalogo.find((n) => n.id === nivel)?.minzoom ?? 0;
}

/** Etiqueta y ayuda del nivel en el selector (AC-V2), tomadas del catálogo. */
export function opcionNivel(catalogo: NivelCatalogo[], nivel: string): { etiqueta: string; ayuda?: string } {
	const n = catalogo.find((x) => x.id === nivel);
	return n ? { etiqueta: n.etiqueta, ...(n.ayuda ? { ayuda: n.ayuda } : {}) } : { etiqueta: nivel };
}

/** Lo que trae indicadores.json para cada indicador. */
export interface IndicadorMapa extends Indicador {
	tema: string;
	/** Niveles con datos (indicadores.json, AC-N2): cualquier id del catálogo, no una lista fija (AC-N13). */
	niveles: string[];
	/** Niveles con valor en al menos 2 territorios: los que pueden ir al mapa (AC-N6, #204). */
	niveles_mapa?: string[];
	/** Si va a la lista del mapa (de educación, solo las tasas calculadas, #213). */
	mapa?: boolean;
	/** Nivel educativo del cuadro del anuario («Primaria», «Media básica»…); vacío en los demás temas (#213). */
	grupo?: string;
	periodos: string[];
}

export function indicadoresDelTema(indicadores: IndicadorMapa[], tema: string): IndicadorMapa[] {
	return indicadores.filter((i) => i.tema === tema);
}

/** El indicador con que abre cada tema; si no está, el primero del tema. Educación: D3 (#214). */
export const INDICADOR_POR_DEFECTO: Record<string, string> = {
	Educación: 'edu_ii_2_2_13_rendimiento_escolar_tasa_promocion_total'
};

/** Orden de los niveles educativos en el selector (#214). */
const ORDEN_GRUPOS = ['Primera infancia e inicial', 'Primaria', 'Media básica', 'Media superior'];

export function indicadorInicialDelTema(indicadores: IndicadorMapa[], tema: string): IndicadorMapa | undefined {
	const del = indicadoresDelTema(indicadores, tema);
	return del.find((i) => i.codigo === INDICADOR_POR_DEFECTO[tema]) ?? del[0];
}

/** AC-E26: los niveles educativos del tema (vacío si el tema no tiene grupos), en el orden del sistema educativo. */
export function gruposDelTema(indicadores: IndicadorMapa[], tema: string): string[] {
	const g = new Set(indicadoresDelTema(indicadores, tema).map((i) => i.grupo ?? '').filter(Boolean));
	return [...g].sort((a, b) => (ORDEN_GRUPOS.indexOf(a) + 1 || 99) - (ORDEN_GRUPOS.indexOf(b) + 1 || 99));
}

/**
 * Los indicadores del tema en el nivel educativo elegido (o todos, si el tema no tiene grupos): primero los totales
 * (sin apertura, «— …» en el nombre) y después las aperturas, en el orden del catálogo.
 */
export function indicadoresDelGrupo(indicadores: IndicadorMapa[], tema: string, grupo: string | null): IndicadorMapa[] {
	const del = indicadoresDelTema(indicadores, tema).filter((i) => !grupo || i.grupo === grupo);
	const apertura = (i: IndicadorMapa) => (i.nombre.includes(' — ') ? 1 : 0);
	return [...del].sort((a, b) => apertura(a) - apertura(b));
}

/** El nivel más detallado del mapa en que el indicador tiene datos, o null. */
export function nivelMasDetallado(ind: IndicadorMapa, catalogo: NivelCatalogo[]): NivelMapa | null {
	return nivelesOfrecidos(ind, catalogo).at(-1) ?? null;
}

/**
 * AC-N9 (M11.4): el mapa solo ofrece niveles con datos, así que nunca avisa «no se publica por…». Queda un aviso
 * solo para el indicador que no tiene ningún nivel en el mapa (AC-N6): lo que se publica por región (los ingresos de
 * la ECH, AC-I20) va con la comparación entre regiones; lo que solo tiene el total del país lo dice.
 */
export function avisoSinMapa(ind: IndicadorMapa, catalogo: NivelCatalogo[]): { mensaje: string; regional: boolean } | null {
	if (nivelesOfrecidos(ind, catalogo).length) return null;
	if (ind.niveles.includes('region')) {
		return { mensaje: `Los ${ind.tema.toLowerCase()} se publican por región: País · Montevideo · Interior.`, regional: true };
	}
	return { mensaje: `«${ind.nombre}» se publica solo para todo el país: no hay datos por territorio para el mapa.`, regional: false };
}

/** AC-N6: cómo se muestra el selector de nivel según cuántos niveles ofrece el indicador. */
export function formaSelectorNivel(ofrecidos: NivelMapa[]): 'oculto' | 'texto' | 'lista' {
	return ofrecidos.length === 0 ? 'oculto' : ofrecidos.length === 1 ? 'texto' : 'lista';
}

/** Niveles que ofrece algún indicador. Solo para los tests visuales, hasta M11.5 (el selector usa nivelesOfrecidos). */
export function nivelesConDatos(indicadores: IndicadorMapa[], catalogo: NivelCatalogo[]): NivelMapa[] {
	return nivelesDibujables(catalogo)
		.filter((n) => indicadores.some((i) => nivelesOfrecidos(i, catalogo).includes(n.id)))
		.map((n) => n.id);
}

/**
 * Si la fuente publica el total del país para este indicador: en este período ('periodo'), solo en otros
 * ('otros', p. ej. la ECH antes de 2025) o nunca ('nunca'). Nunca se calcula sumando territorios.
 */
export function totalDelPais(
	valoresPais: { indicadores: Record<string, Record<string, Record<string, number | null>>> } | null,
	indicador: string,
	periodo: string
): 'periodo' | 'otros' | 'nunca' {
	const porPeriodo = valoresPais?.indicadores[indicador];
	if (!porPeriodo || !Object.values(porPeriodo).some((v) => v.UY != null)) return 'nunca';
	return porPeriodo[periodo]?.UY != null ? 'periodo' : 'otros';
}

/** "Municipio (Montevideo)" -> "municipio (Montevideo)". */
export function minuscula(s: string): string {
	return s.charAt(0).toLowerCase() + s.slice(1);
}

// ---------------------------------------------------------------- período y fuente (AC-L24)

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'set', 'oct', 'nov', 'dic'];

/** "2026-07/2026-09" -> "Trimestre móvil jul–set 2026"; "2025-12/2026-02" -> "Trimestre móvil dic 2025–feb 2026". */
export function etiquetaPeriodo(periodo: string): string {
	// F3.7b: trimestre calendario «2026-T3» -> «jul–set 2026»
	const t = /^(\d{4})-T([1-4])$/.exec(periodo);
	if (t) return `${MESES[(Number(t[2]) - 1) * 3]}–${MESES[Number(t[2]) * 3 - 1]} ${t[1]}`;
	const m = /^(\d{4})-(\d{2})\/(\d{4})-(\d{2})$/.exec(periodo);
	if (!m) return periodo;
	const [, a1, m1, a2, m2] = m;
	const desde = MESES[Number(m1) - 1];
	const hasta = MESES[Number(m2) - 1];
	if (!desde || !hasta) return periodo;
	return a1 === a2 ? `Trimestre móvil ${desde}–${hasta} ${a2}` : `Trimestre móvil ${desde} ${a1}–${hasta} ${a2}`;
}

/**
 * "INE, ECH · Trimestre móvil jul–set 2026". Si el período es un año que la fuente ya nombra, no se repite:
 * "INE, Unidades geoestadísticas Censo 2023", no "… Censo 2023 · 2023" (AC-V17).
 */
export function fuenteYPeriodo(fuente: string, periodo: string): string {
	if (!periodo) return fuente;
	const yaEsta = /^\d{4}$/.test(periodo) && new RegExp(`(^|\\D)${periodo}(\\D|$)`).test(fuente);
	return yaEsta ? fuente : `${fuente} · ${periodo}`;
}

/** "INE, ECH" si el nombre de la fuente termina con su sigla entre paréntesis; si no, "INE, <nombre>". */
export function fuenteCorta(f: { organismo: string; nombre: string }): string {
	const siglas = (s: string) => /\(([^()]+)\)\s*$/.exec(s)?.[1];
	const org = siglas(f.organismo) ?? f.organismo;
	const nom = siglas(f.nombre) ?? f.nombre;
	// «MEC, MEC» no dice nada: si la sigla del nombre es la del organismo, va el nombre sin la sigla (#214)
	return nom === org ? `${org}, ${f.nombre.replace(/\s*\([^()]+\)\s*$/, '')}` : `${org}, ${nom}`;
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

/**
 * Etiquetas de la leyenda en es-UY: "Hasta 1.234", "1.235 a 5.000", "Más de 5.000". Si los valores tienen
 * decimales (tasas, miles de personas), con un decimal y saltos de 0,1: "Hasta 59,4", "59,5 a 62,6".
 */
export function etiquetasLeyenda(c: Clases): string[] {
	const conDecimales = [c.min, c.max, ...c.cortes].some((v) => !Number.isInteger(v));
	const d = conDecimales ? 1 : undefined;
	const paso = conDecimales ? 0.1 : 1;
	const f = (v: number) => numero(v, d);
	if (!c.cortes.length) return [c.min === c.max ? f(c.min) : `${f(c.min)} a ${f(c.max)}`];
	return [
		`Hasta ${f(c.cortes[0])}`,
		...c.cortes.slice(1).map((corte, i) => `${f(c.cortes[i] + paso)} a ${f(corte)}`),
		`Más de ${f(c.cortes.at(-1)!)}`
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

/**
 * AC-M5 / AC-N8: el estado desde la URL. Un `nivel` que no se ofrece para el indicador (un enlace viejo o escrito a
 * mano) se cambia con la regla de AC-N7; la página reescribe la URL con replaceState, sin aviso.
 */
export function estadoDesdeUrl(params: URLSearchParams, indicadores: IndicadorMapa[], catalogo: NivelCatalogo[]): EstadoMapa {
	const ind = indicadores.find((i) => i.codigo === params.get('indicador')) ?? indicadores[0];
	const dibujables = nivelesDibujables(catalogo).map((n) => n.id);
	const pedido = params.get('nivel') ?? '';
	const base = catalogo.some((n) => n.id === pedido) ? pedido : (dibujables[0] ?? 'departamento');
	// Sin niveles dibujables para el indicador (solo país y región, AC-I20): queda el pedido si se dibuja, o el más grueso.
	const nivel =
		nivelAlCambiar(base, nivelesOfrecidos(ind, catalogo), catalogo) ?? (dibujables.includes(base) ? base : (dibujables[0] ?? 'departamento'));
	const periodo = ind?.periodos.includes(params.get('periodo') ?? '') ? params.get('periodo')! : (ind?.periodos.at(-1) ?? '');
	const t = params.get('territorio');
	const valido = t && /^[a-z_]+\/[0-9A-Za-z-]+$/.test(t) ? t : null;
	// AC-N8 + AC-V8: si el nivel se corrigió, el territorio sigue la regla de selección (nunca uno de otro nivel).
	const territorio = valido && nivel !== pedido ? territorioAlCambiarNivel(valido, nivel, catalogo) : valido;
	return { indicador: ind?.codigo ?? '', nivel, periodo, territorio };
}

/**
 * AC-V8 sin la ficha (al abrir desde la URL): el territorio se conserva si es del nivel; si el nivel nuevo lo contiene
 * (`dentro_de`) y el padre se sabe por el código, pasa al padre: sección y segmento → su departamento (los dos primeros
 * dígitos del código INE), lo de Montevideo → departamento 01. Si no, la selección se vacía.
 */
export function territorioAlCambiarNivel(territorio: string, nivel: NivelMapa, catalogo: NivelCatalogo[]): string | null {
	const [desde, codigo] = territorio.split('/');
	if (desde === nivel) return territorio;
	const origen = catalogo.find((n) => n.id === desde);
	if (nivel !== 'departamento' || !origen?.dentro_de.includes('departamento')) return null;
	if (origen.ambito === 'montevideo') return 'departamento/01';
	if (desde === 'seccion' || desde === 'segmento') return `departamento/${codigo.slice(0, 2)}`;
	return null;
}

export function urlDesdeEstado(e: EstadoMapa): string {
	const p = new URLSearchParams({ indicador: e.indicador, nivel: e.nivel, periodo: e.periodo });
	if (e.territorio) p.set('territorio', e.territorio);
	return `?${p.toString()}`;
}

/** AC-I20: los territorios de la comparación regional, en orden, con su nombre corto. */
export const COMPARACION_REGIONAL = [
	{ nivel: 'pais', codigo: 'UY', nombre: 'Total país' },
	{ nivel: 'departamento', codigo: '01', nombre: 'Montevideo' },
	{ nivel: 'region', codigo: 'interior', nombre: 'Interior' },
	{ nivel: 'region', codigo: 'interior-5000', nombre: 'Interior: localidades de 5.000 o más' },
	{ nivel: 'region', codigo: 'interior-menores', nombre: 'Interior: localidades pequeñas y rurales' }
] as const;

type ValoresPorNivel = Partial<Record<string, { indicadores: Record<string, Record<string, Record<string, number | null>>> } | null>>;

/** AC-I20: valor de cada territorio de la comparación para el indicador y el período (null si no está publicado). */
export function filasComparacion(valores: ValoresPorNivel, indicador: string, periodo: string) {
	return COMPARACION_REGIONAL.map((t) => ({
		...t,
		valor: valores[t.nivel]?.indicadores[indicador]?.[periodo]?.[t.codigo] ?? null
	}));
}
