// Lógica de las fichas (M7) sin DOM: secciones por tema, nota de suma no aditiva y cita.

import { NOMBRE_NIVEL, type Captura, type Ficha, type FuenteRef, type Observacion, type Resumen } from '../datos.ts';
import { fecha, numero, porcentaje } from '../formato.ts';

/** Secciones de la ficha y los temas de indicadores que agrupan (SYSTEM.md §8). */
export const SECCIONES_FICHA = [
	{ id: 'poblacion', titulo: 'Población', temas: ['Población'] },
	{ id: 'vivienda', titulo: 'Vivienda y hogares', temas: ['Vivienda', 'Hogares'] },
	{ id: 'trabajo', titulo: 'Trabajo e ingresos', temas: ['Trabajo', 'Ingresos'] },
	{ id: 'educacion', titulo: 'Educación', temas: ['Educación'] }
] as const;

export const SIN_FUENTES = 'Todavía no hay fuentes cargadas para este tema.';

/** Observaciones de una sección de la ficha (las de sus temas), en el orden del catálogo. */
export function observacionesDeSeccion(f: Ficha, temas: readonly string[]): Observacion[] {
	// Los totales (…_total) primero; después, por nombre.
	const clave = (o: Observacion) => [o.indicador.endsWith('_total') ? 0 : 1, f.indicadores[o.indicador]?.nombre ?? o.indicador] as const;
	return f.observaciones
		.filter((o) => temas.includes(f.indicadores[o.indicador]?.tema ?? ''))
		.sort((a, b) => clave(a)[0] - clave(b)[0] || clave(a)[1].localeCompare(clave(b)[1], 'es'));
}

/**
 * F2.8c: separa los valores de un solo período (Censo) de las series (p. ej. trimestres móviles de la ECH),
 * agrupadas por indicador y en orden de período, para mostrarlas como gráfico (AC-L25).
 */
export function separarSeries(lista: Observacion[]): { puntuales: Observacion[]; series: Map<string, Observacion[]> } {
	const puntuales: Observacion[] = [];
	const series = new Map<string, Observacion[]>();
	for (const o of lista) {
		if (o.tipo_periodo === 'censo') puntuales.push(o);
		else series.set(o.indicador, [...(series.get(o.indicador) ?? []), o]);
	}
	for (const s of series.values()) s.sort((a, b) => a.periodo_fin.localeCompare(b.periodo_fin));
	return { puntuales, series };
}

export interface PuntoSerie {
	periodo: string;
	periodo_fin: string;
	valor: number;
}

/**
 * Puntos del gráfico: la serie del territorio y la del total del país tal como la publica la fuente, desde el
 * primer informe que la trae (decisión del mantenedor, #67). Nunca se suma territorios (SYSTEM.md §4).
 */
export function puntosSerie(
	territorio: Observacion[],
	pais: Ficha | null,
	indicador: string
): { periodos: string[]; territorio: PuntoSerie[]; pais: PuntoSerie[] } {
	const punto = (o: Observacion): PuntoSerie | null =>
		o.valor === null ? null : { periodo: o.periodo, periodo_fin: o.periodo_fin, valor: o.valor };
	const delPais = (pais?.observaciones ?? [])
		.filter((o) => o.indicador === indicador && o.tipo_periodo !== 'censo')
		.sort((a, b) => a.periodo_fin.localeCompare(b.periodo_fin));
	const periodos = territorio.map((o) => o.periodo);
	const enEje = new Set(periodos);
	return {
		periodos,
		territorio: territorio.map(punto).filter((p): p is PuntoSerie => p !== null),
		// solo los períodos del eje (los del territorio): lo que se dibuja es lo que se cuenta
		pais: delPais.map(punto).filter((p): p is PuntoSerie => p !== null && enEje.has(p.periodo))
	};
}

/** Valor de un indicador en un territorio resumido (padre o contenido). */
export function valorDe(r: Resumen, indicador: string, periodo: string): number | null {
	return r.valores[indicador]?.[periodo] ?? null;
}

/** "x % de <padre>": proporción del valor publicado del territorio sobre el del padre (no es una suma). */
export function partes(o: Observacion, f: Ficha): { texto: string; padre: Resumen }[] {
	if (o.valor === null) return [];
	return f.padres
		.map((p) => ({ p, v: valorDe(p, o.indicador, o.periodo) }))
		.filter(({ v }) => v !== null && v > 0)
		.map(({ p, v }) => ({ texto: `${porcentaje(o.valor! / v!)} de ${p.nombre}`, padre: p }))
		.reverse();
}

/**
 * AC-F4: en un departamento, si la suma de los valores publicados de sus secciones no coincide con el
 * valor publicado del departamento, el texto que lo explica. Solo para mostrar: nada se guarda ni se pinta.
 */
export function notaNoAditiva(f: Ficha, indicador = 'pob_total', periodo = '2023'): string | null {
	if (f.nivel !== 'departamento') return null;
	const propio = f.observaciones.find((o) => o.indicador === indicador && o.periodo === periodo)?.valor;
	const secciones = f.contenidos.seccion ?? [];
	const valores = secciones.map((s) => valorDe(s, indicador, periodo));
	if (propio == null || !secciones.length || valores.some((v) => v === null)) return null;
	const suma = valores.reduce<number>((a, v) => a + (v ?? 0), 0);
	if (suma === propio) return null;
	const nombre = f.indicadores[indicador]?.nombre.toLowerCase() ?? indicador;
	return (
		`La suma de las ${secciones.length} secciones (${numero(suma)} ${nombre}) no coincide con el total del ` +
		`departamento (${numero(propio)}): la diferencia es de ${numero(propio - suma)} (${porcentaje((propio - suma) / propio)}). ` +
		'El INE ubica a parte de las personas enumeradas por registros administrativos solo a nivel de localidad ' +
		'o de departamento, por eso la suma de unidades menores no coincide con el total de la unidad mayor. ' +
		'Cada valor se muestra tal como lo publica el INE para su nivel.'
	);
}

/** AC-F6: texto para citar la ficha. */
export function cita(f: Ficha, url: string, accedido: Date): string {
	const fuentes = [...new Set(Object.values(f.fuentes).map((x) => `${x.organismo}, ${x.nombre}`))].join('; ');
	return (
		`Observatorio Uruguay. «${f.nombre}» (${NOMBRE_NIVEL[f.nivel].toLowerCase()}, código INE ${f.codigo}). ` +
		`Datos: ${fuentes}. ${url}. Consultado el ${fecha(accedido.toISOString())}.`
	);
}

/** URL del mapa con este territorio seleccionado. */
export function consultaMapa(t: { nivel: string; codigo: string }): string {
	const nivel = ['departamento', 'seccion', 'segmento'].includes(t.nivel) ? t.nivel : 'departamento';
	return `?indicador=pob_total&nivel=${nivel}&periodo=2023&territorio=${t.nivel}/${t.codigo}`;
}

/** Una fuente de la ficha con todas sus capturas, de la más reciente a la más vieja (AC-V18). */
export interface FuenteDeFicha {
	id: string;
	fuente: FuenteRef | undefined;
	capturas: Captura[];
	ultima: Captura;
}

/**
 * «Fuentes de esta ficha»: una entrada por fuente (no una por captura). La ECH tiene una captura por
 * informe mensual; repetir nombre y licencia en cada una alargaba la ficha a miles de px (V-14).
 */
export function fuentesDeFicha(f: Pick<Ficha, 'capturas' | 'fuentes'>): FuenteDeFicha[] {
	const grupos = new Map<string, Captura[]>();
	for (const c of Object.values(f.capturas)) grupos.set(c.fuente_id, [...(grupos.get(c.fuente_id) ?? []), c]);
	return [...grupos].map(([id, capturas]) => {
		const orden = [...capturas].sort((a, b) => b.fecha_proceso.localeCompare(a.fecha_proceso) || b.archivo.localeCompare(a.archivo));
		return { id, fuente: f.fuentes[id], capturas: orden, ultima: orden[0] };
	});
}

/**
 * AC-V20: marcas del eje y en valores redondos (paso de 1, 2, 2,5 o 5 × 10ⁿ), entre 4 y 6 intervalos, que
 * cubren [min, max]. El eje va de la primera a la última marca.
 */
export function marcasRedondas(min: number, max: number): number[] {
	if (!(max > min)) {
		const d = Math.abs(min) * 0.1 || 1;
		return marcasRedondas(min - d, max + d);
	}
	const potencia = 10 ** Math.floor(Math.log10((max - min) / 5));
	const e = 1e-9; // tolerancia de coma flotante
	const intervalos = (p: number) => Math.ceil(max / p - e) - Math.floor(min / p + e);
	// el paso redondo más chico que deja como mucho 5 intervalos una vez redondeados los extremos
	const paso = [1, 2, 2.5, 5, 10, 20, 25, 50].map((m) => m * potencia).find((p) => intervalos(p) <= 5) ?? 100 * potencia;
	const desde = Math.floor(min / paso + e) * paso;
	const hasta = Math.ceil(max / paso - e) * paso;
	const marcas: number[] = [];
	for (let v = desde; v <= hasta + paso / 2; v += paso) marcas.push(Number(v.toFixed(10)));
	return marcas;
}

/** AC-V20: índices de los períodos que llevan etiqueta en el eje x (n repartidos, el primero y el último incluidos). */
export function indicesEtiquetas(cantidad: number, n = 5): number[] {
	if (cantidad <= n) return Array.from({ length: cantidad }, (_, i) => i);
	return Array.from({ length: n }, (_, i) => Math.round((i * (cantidad - 1)) / (n - 1)));
}

/** AC-V20: decimales para mostrar juntos valores comparables (territorio y país): los del que más tiene (hasta 2). */
export function decimalesComunes(valores: number[]): number {
	return Math.min(2, Math.max(0, ...valores.map((v) => (String(v).split('.')[1] ?? '').length)));
}
