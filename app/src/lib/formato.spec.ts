import { describe, expect, it } from 'vitest';
import { conUnidad, fecha, numero, porcentaje, publicado, tamano } from './formato';

describe('formato es-UY (AC-G1)', () => {
	it('usa punto para miles y coma para decimales', () => {
		expect(numero(1300197)).toBe('1.300.197');
		expect(numero(3495947)).toBe('3.495.947');
		expect(numero(12.5, 1)).toBe('12,5');
		expect(publicado(14.9)).toBe('14,9');
		expect(publicado(26271)).toBe('26.271');
		expect(publicado(null)).toBe('—');
		expect(numero(1234.5678, 2)).toBe('1.234,57');
	});

	it('agrupa también los números de 4 cifras', () => {
		expect(numero(4538)).toBe('4.538');
	});

	it('muestra una raya cuando no hay valor', () => {
		expect(numero(null)).toBe('—');
		expect(numero(undefined)).toBe('—');
		expect(numero(Number.NaN)).toBe('—');
	});

	it('porcentajes, unidades, fechas y tamaños', () => {
		expect(porcentaje(0.0161)).toBe('1,6 %');
		expect(conUnidad(26271, 'personas')).toBe('26.271 personas');
		expect(fecha('2026-11-17T11:41:20+00:00')).toBe('17/11/2026');
		expect(fecha('2026-11-17T01:00:00+00:00')).toBe('16/11/2026'); // hora de Montevideo
		expect(tamano(14407563)).toBe('14,4 MB');
	});
});
