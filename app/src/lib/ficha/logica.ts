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
 * AC-V24: si una sección no tiene datos al nivel de la ficha, el nivel más cercano que la contiene y sí los
 * tiene, con los temas que publica ahí («Trabajo: se publica por departamento → ver San José»). null si
 * ningún nivel que la contiene tiene datos de esos temas.
 */
export function datosEnPadre(f: Pick<Ficha, 'padres' | 'indicadores'>, temas: readonly string[]): { padre: Resumen; temas: string[] } | null {
	for (const padre of [...f.padres].reverse()) {
		const conDatos = temas.filter((t) => Object.keys(padre.valores).some((k) => f.indicadores[k]?.tema === t));
		if (conDatos.length) return { padre, temas: conDatos };
	}
	return null;
}

/**
 * AC-I22 (F3.7a): temas de la sección que no tienen datos en la ficha ni en un nivel que la contiene, pero sí en la
 * región del Interior (p. ej. los ingresos de un departamento que no es Montevideo).
 */
export function datosEnRegion(
	f: Pick<Ficha, 'observaciones' | 'indicadores' | 'padres' | 'region'>,
	temas: readonly string[]
): { region: NonNullable<Ficha['region']>; temas: string[] } | null {
	if (!f.region) return null;
	const propios = new Set(f.observaciones.map((o) => f.indicadores[o.indicador]?.tema));
	const arriba = new Set(datosEnPadre(f, temas)?.temas ?? []);
	const enRegion = temas.filter((t) => !propios.has(t) && !arriba.has(t) && f.region!.temas.includes(t));
	return enRegion.length ? { region: f.region, temas: enRegion } : null;
}

/** AC-I23 (F3.7a): qué es cada región, en una frase. */
export const DESCRIPCION_REGION: Record<string, string> = {
	interior: 'Todos los departamentos salvo Montevideo.',
	'interior-5000': 'Las localidades de 5.000 o más habitantes de todos los departamentos salvo Montevideo.',
	'interior-menores': 'Las localidades de menos de 5.000 habitantes y las zonas rurales de todos los departamentos salvo Montevideo.'
};

/**
 * AC-V20: marcas del eje y en valores redondos (paso de 1, 2, 2,5 o 5 × 10ⁿ), como mucho 5 intervalos, que
 * cubren [min, max]. El eje va de la primera a la última marca.
 */
export function marcasRedondas(min: number, max: number): number[] {
	if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
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

/**
 * AC-V27: densidad de población (personas por km²). No es una observación: la calcula la app al mostrar la
 * ficha con la población del Censo y la superficie de la geometría del INE (decisión del mantenedor, #111).
 * null si falta alguno de los dos datos.
 */
export function densidad(personas: number | null, km2: number | null): number | null {
	if (personas === null || km2 === null || !(km2 > 0)) return null;
	return personas / km2;
}

/** F3.7b (AC-I21): las opciones de la serie de ingresos y el indicador que les corresponde. */
export interface OpcionesIngreso {
	medida: 'hogar' | 'pc';
	aguinaldo: boolean;
	valorLocativo: boolean;
	base: 'corrientes' | 'ene2005';
	frecuencia: 'trimestre' | 'anio';
}

/** Por defecto, la variante titular del INE: hogares, sin aguinaldo, sin valor locativo, corrientes (F3.1, #134). */
export const INGRESO_POR_DEFECTO: OpcionesIngreso = {
	medida: 'hogar',
	aguinaldo: false,
	valorLocativo: false,
	base: 'corrientes',
	frecuencia: 'trimestre'
};

/** Código del indicador. A precios de enero de 2005 el INE publica solo sin aguinaldo y sin valor locativo. */
export function indicadorIngreso(o: OpcionesIngreso): string {
	if (o.base === 'ene2005') return `ing_${o.medida}_medio_sagu_svl_ene2005`;
	return `ing_${o.medida}_medio_${o.aguinaldo ? 'cagu' : 'sagu'}_${o.valorLocativo ? 'cvl' : 'svl'}`;
}

/** Las observaciones del indicador elegido en la frecuencia elegida (trimestres o totales anuales). */
export function serieIngreso(series: Map<string, Observacion[]>, o: OpcionesIngreso): Observacion[] {
	return (series.get(indicadorIngreso(o)) ?? []).filter((x) => x.tipo_periodo === o.frecuencia);
}

// ---------------------------------------------------------------- educación (F4.7b1, #210)

/** Nivel educativo según el código del cuadro del anuario del MEC: II-<nivel>.<grupo>.<n>. */
export const NIVELES_EDUCATIVOS: Record<string, string> = {
	'1': 'Primera infancia e inicial',
	'2': 'Primaria',
	'3': 'Media básica',
	'4': 'Media superior'
};
/** Grupo de AC-E27 según el segundo número del código: .1 centros, .2 estudiantes, .3 docentes. */
export const GRUPOS_EDUCACION: Record<string, string> = { '1': 'Centros', '2': 'Estudiantes', '3': 'Docentes' };

export interface ValorEducacion {
	observacion: Observacion;
	/** Qué mide dentro del cuadro: la apertura («FORMA DE ADMINISTRACIÓN/PÚBLICA/TOTAL») o el nombre de la tasa. */
	etiqueta: string;
	unidad: string;
	calculado: boolean;
}

export interface CuadroEducacion {
	cuadro: string;
	titulo: string;
	/** Año del último valor publicado del cuadro. */
	anio: string;
	/** El valor que resume el cuadro (la tasa total calculada, o el TOTAL publicado); null si el cuadro no tiene. */
	principal: ValorEducacion | null;
	/** Las demás aperturas del mismo año (van en el bloque plegable). */
	aperturas: ValorEducacion[];
	/** Pie del cuadro (notas, AC-E29). */
	nota: string;
	/** «Fuente: MEC, Anuario Estadístico de Educación 2024, cuadro II-2.2.1» (AC-E29). */
	fuente: string;
}

/** La ruta de la columna de origen de un indicador del anuario («FORMA DE ADMINISTRACIÓN/PÚBLICA/TOTAL»). */
function rutaEducacion(ind: { columna_origen: string }): string {
	return ind.columna_origen.split(' · ').slice(1).join(' · ');
}

/** Siglas que aparecen en las aperturas del anuario: quedan en mayúsculas. */
const SIGLAS = new Set(['ANEP', 'CAIF', 'CEIP', 'CES', 'CETP', 'DGEIP', 'DGES', 'DGETP', 'INAU', 'JICI', 'MEC', 'UTU']);

/** «FORMA DE ADMINISTRACIÓN/PÚBLICA/TOTAL» → «Forma de administración · Pública · Total»: legible, sin cambiar palabras. */
export function rutaLegible(ruta: string): string {
	return ruta
		.split('/')
		.map((t) => t.trim())
		.map((t) => (t === t.toUpperCase() && /\p{L}{2}/u.test(t) && !SIGLAS.has(t) ? t.charAt(0) + t.slice(1).toLowerCase() : t))
		.join(' · ');
}

type IndicadorEducacion = { columna_origen: string; nombre: string; es_derivado?: boolean; formula?: string };

/**
 * Lo que mide un indicador del anuario dentro de su cuadro: su apertura legible. Una tasa de promoción calculada toma
 * la apertura del indicador «promovidos» de su fórmula (con la ortografía del archivo), sin los tramos de rendimiento,
 * para que dos tasas del mismo cuadro nunca se llamen igual.
 */
function etiquetaEducacion(ind: IndicadorEducacion, indicadores: Record<string, IndicadorEducacion>): string {
	if (!ind.es_derivado) {
		// la categoría de un indicador con «__» (p. ej. «— diurna») va en el nombre: sin ella, dos columnas se leerían igual
		const categoria = ind.nombre.includes(' — ') ? ind.nombre.split(' — ').at(-1) : '';
		return (rutaLegible(rutaEducacion(ind)) || ind.nombre) + (categoria ? ` — ${categoria}` : '');
	}
	const prom = indicadores[(ind.formula ?? '').split(' / ')[0].trim()];
	if (!prom || !/tasa de promoci/i.test(ind.nombre)) return ind.nombre;
	const tramos = rutaEducacion(prom)
		.split('/')
		.filter((t) => !/^(rendimiento( escolar| educativo)?|promovidos?)$/i.test(t.trim()));
	const apertura = rutaLegible(tramos.filter((t) => t.trim().toUpperCase() !== 'TOTAL').join('/'));
	return apertura ? `Tasa de promoción · ${apertura}` : 'Tasa de promoción (total)';
}

/** El id de la tasa de promoción total de un cuadro: solo «total» o «rendimiento» entre el código y la tasa. */
const TASA_TOTAL = /^edu_ii_\d+_\d+_\d+_(total_)?(rendimiento(_escolar)?_)?tasa_promocion(_total)?$/;

/**
 * AC-E27 / AC-E29 (decisión del mantenedor en #210: una fila por cuadro, con el detalle plegado): los valores de
 * educación de la ficha agrupados por nivel educativo, grupo (centros, estudiantes, docentes) y cuadro, con el valor
 * que resume cada cuadro en su último año, sus aperturas, la nota del cuadro y la fuente con el año del anuario.
 */
export function cuadrosEducacion(
	f: Pick<Ficha, 'observaciones' | 'indicadores' | 'capturas'>
): { nivel: string; grupos: { grupo: string; cuadros: CuadroEducacion[] }[] }[] {
	const porCuadro = new Map<string, Observacion[]>();
	for (const o of f.observaciones) {
		const c = f.indicadores[o.indicador]?.cuadro;
		if (c && f.indicadores[o.indicador]?.tema === 'Educación') porCuadro.set(c, [...(porCuadro.get(c) ?? []), o]);
	}
	const cuadros: (CuadroEducacion & { nivel: string; grupo: string })[] = [];
	for (const [cuadro, lista] of porCuadro) {
		const m = /^II-(\d+)\.(\d+)\./.exec(cuadro);
		if (!m) continue;
		const anio = lista.map((o) => o.periodo).sort().at(-1)!;
		const delAnio = lista.filter((o) => o.periodo === anio);
		const valores: ValorEducacion[] = delAnio.map((o) => {
			const ind = f.indicadores[o.indicador];
			return { observacion: o, etiqueta: etiquetaEducacion(ind, f.indicadores), unidad: ind.unidad, calculado: !!ind.es_derivado };
		});
		// El resumen, solo si es único: la tasa de promoción total calculada (rendimiento); si no, el total publicado del
		// cuadro («TOTAL», o el total de su única dimensión, «FORMA DE ADMINISTRACIÓN/TOTAL»). Nunca una suma (§4).
		const unico = (xs: ValorEducacion[]) => (xs.length === 1 ? xs[0] : null);
		const rutaDe = (v: ValorEducacion) => rutaEducacion(f.indicadores[v.observacion.indicador]);
		const publicados = valores.filter((v) => !v.calculado);
		const principal =
			unico(valores.filter((v) => v.calculado && TASA_TOTAL.test(v.observacion.indicador))) ??
			unico(publicados.filter((v) => rutaDe(v) === 'TOTAL')) ??
			unico(publicados.filter((v) => /^[^/]+\/TOTAL$/.test(rutaDe(v)))) ??
			null;
		const base = Object.keys(f.indicadores).find((k) => f.indicadores[k].cuadro === cuadro && !f.indicadores[k].es_derivado);
		const titulo = (base ? f.indicadores[base].nombre.split(': ')[0] : cuadro).replace(/ según departamento$/i, '');
		const archivo = f.capturas[(principal ?? valores[0]).observacion.captura_id]?.archivo ?? '';
		const anioAnuario = /(\d{4})\.\w+$/.exec(archivo)?.[1] ?? anio;
		cuadros.push({
			cuadro,
			titulo,
			anio,
			principal,
			aperturas: valores.filter((v) => v !== principal).sort((a, b) => a.etiqueta.localeCompare(b.etiqueta, 'es')),
			nota: (base && f.indicadores[base].nota) || '',
			fuente: `Fuente: MEC, Anuario Estadístico de Educación ${anioAnuario}, cuadro ${cuadro}`,
			nivel: NIVELES_EDUCATIVOS[m[1]] ?? `Nivel ${m[1]}`,
			grupo: GRUPOS_EDUCACION[m[2]] ?? 'Otros'
		});
	}
	const orden = (c: string) => c.split(/[-.]/).slice(1).map(Number);
	cuadros.sort((a, b) => {
		const [x, y] = [orden(a.cuadro), orden(b.cuadro)];
		for (let i = 0; i < Math.max(x.length, y.length); i++) if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) - (y[i] ?? 0);
		return 0;
	});
	const salida: { nivel: string; grupos: { grupo: string; cuadros: CuadroEducacion[] }[] }[] = [];
	for (const c of cuadros) {
		let n = salida.find((x) => x.nivel === c.nivel);
		if (!n) salida.push((n = { nivel: c.nivel, grupos: [] }));
		let g = n.grupos.find((x) => x.grupo === c.grupo);
		if (!g) n.grupos.push((g = { grupo: c.grupo, cuadros: [] }));
		g.cuadros.push(c);
	}
	return salida;
}

/** AC-E28: lo que dice una ficha sin datos propios de un tema que se publica en un nivel que la contiene. */
export function textoEnPadre(temas: string[], nivelPadre: string): string {
	// Educación se publica solo por departamento (y país e Interior): el texto lo dice así (AC-E28).
	if (temas.length === 1 && temas[0] === 'Educación' && nivelPadre === 'departamento') return 'Educación: datos por departamento';
	return `${temas.join(' e ')}: se publica por ${(NOMBRE_NIVEL[nivelPadre as keyof typeof NOMBRE_NIVEL] ?? nivelPadre).toLowerCase()}`;
}
