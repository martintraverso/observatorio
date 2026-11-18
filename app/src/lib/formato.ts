// Formato de números y fechas en español de Uruguay (AC-G1):
// punto como separador de miles y coma decimal: 1.300.197 · 12,5.

const LOCALE = 'es-UY';

const enteros = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0, useGrouping: 'always' });

/** 1300197 -> "1.300.197". Por defecto sin decimales; `decimales` fija la cantidad. */
/** Un valor tal como lo publica la fuente: sin redondear a entero (p. ej. 14,9 miles de personas de la ECH). */
export function publicado(valor: number | null | undefined): string {
	if (valor === null || valor === undefined || Number.isNaN(valor)) return '—';
	return new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2, useGrouping: 'always' }).format(valor);
}

export function numero(valor: number | null | undefined, decimales?: number): string {
	if (valor === null || valor === undefined || Number.isNaN(valor)) return '—';
	if (decimales === undefined) return enteros.format(valor);
	return new Intl.NumberFormat(LOCALE, {
		minimumFractionDigits: decimales,
		maximumFractionDigits: decimales,
		useGrouping: 'always'
	}).format(valor);
}

/** 0.0161 -> "1,6 %". */
export function porcentaje(fraccion: number | null | undefined, decimales = 1): string {
	if (fraccion === null || fraccion === undefined || Number.isNaN(fraccion)) return '—';
	return `${numero(fraccion * 100, decimales)} %`;
}

/** Valor con su unidad: (1300197, "personas") -> "1.300.197 personas". */
export function conUnidad(valor: number | null | undefined, unidad: string): string {
	return `${numero(valor)} ${unidad}`;
}

/** "2026-11-17T11:41:20+00:00" -> "17/11/2026". */
export function fecha(iso: string | null | undefined): string {
	if (!iso) return '—';
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return '—';
	return new Intl.DateTimeFormat(LOCALE, {
		day: '2-digit',
		month: '2-digit',
		year: 'numeric',
		timeZone: 'America/Montevideo'
	}).format(d);
}

/** Tamaño de archivo: 14407563 -> "14,4 MB". */
export function tamano(bytes: number): string {
	if (bytes < 1e3) return `${numero(bytes)} B`;
	if (bytes < 1e6) return `${numero(bytes / 1e3, 1)} kB`;
	return `${numero(bytes / 1e6, 1)} MB`;
}
