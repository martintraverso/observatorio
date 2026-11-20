import { describe, expect, it } from 'vitest';
import type { Fuente } from './datos';
import { datosCatalogo, filtrar, nivelesDetallados, historialDe, resumen, SIN_FILTROS, ultimaCaptura, type CapturaHistorial } from './fuentes';

const f = (id: string, organismo: string, estado: string, niveles: string[], temas: string[]) =>
	({ id, nombre: id.toUpperCase(), organismo, estado, niveles_publicados: niveles, temas }) as unknown as Fuente;

const FUENTES = [
	f('censo', 'INE', 'activa', ['departamento', 'segmento'], ['Población']),
	f('ech', 'INE', 'en preparación', ['departamento'], ['Trabajo', 'Ingresos']),
	f('siniestros', 'UNASEV', 'a relevar', ['segmento'], ['Seguridad vial'])
];

const c = (fuente_id: string, fecha: string, resultado: CapturaHistorial['resultado']) =>
	({ id: `${fuente_id}:x`, fuente_id, archivo: 'a.zip', sha256: 'x', fecha_proceso: fecha, resultado, detalle: '' }) as CapturaHistorial;

const HISTORIAL = [
	c('censo', '2026-11-16T10:00:00+00:00', 'nuevo'),
	c('censo', '2026-11-17T10:00:00+00:00', 'sin cambios'),
	c('censo', '2026-11-18T10:00:00+00:00', 'error')
];

describe('AC-SRC2: filtros combinables', () => {
	it('sin filtros devuelve todo', () => {
		expect(filtrar(FUENTES, SIN_FILTROS)).toHaveLength(3);
	});

	it('cada filtro y su combinación', () => {
		expect(filtrar(FUENTES, { ...SIN_FILTROS, organismo: 'INE' }).map((x) => x.id)).toEqual(['censo', 'ech']);
		expect(filtrar(FUENTES, { ...SIN_FILTROS, nivel: 'segmento' }).map((x) => x.id)).toEqual(['censo', 'siniestros']);
		expect(filtrar(FUENTES, { ...SIN_FILTROS, estado: 'activa' }).map((x) => x.id)).toEqual(['censo']);
		expect(filtrar(FUENTES, { ...SIN_FILTROS, organismo: 'INE', nivel: 'segmento' }).map((x) => x.id)).toEqual(['censo']);
		expect(filtrar(FUENTES, { ...SIN_FILTROS, organismo: 'UNASEV', estado: 'activa' })).toEqual([]);
	});

	it('el texto busca en nombre, organismo y temas, sin tildes', () => {
		expect(filtrar(FUENTES, { ...SIN_FILTROS, texto: 'poblacion' }).map((x) => x.id)).toEqual(['censo']);
		expect(filtrar(FUENTES, { ...SIN_FILTROS, texto: 'unasev' }).map((x) => x.id)).toEqual(['siniestros']);
	});
});

describe('capturas', () => {
	it('historial de la más nueva a la más vieja y última captura procesada', () => {
		expect(historialDe(HISTORIAL, 'censo').map((x) => x.resultado)).toEqual(['error', 'sin cambios', 'nuevo']);
		expect(ultimaCaptura(HISTORIAL, 'censo')?.fecha_proceso).toBe('2026-11-16T10:00:00+00:00');
		expect(ultimaCaptura(HISTORIAL, 'ech')).toBeNull();
	});

	it('resumen por estado y última revisión', () => {
		const r = resumen(FUENTES, HISTORIAL);
		expect(r.porEstado).toEqual({ activa: 1, 'en preparación': 1, 'a relevar': 1 });
		expect(r.ultimaRevision).toBe('2026-11-18T10:00:00+00:00');
	});
});

describe('datosCatalogo (#96, AC-G6)', () => {
	it('trae el resumen y la última captura por fuente, sin el historial', () => {
		const d = datosCatalogo(FUENTES, HISTORIAL);
		expect(d.resumen).toEqual(resumen(FUENTES, HISTORIAL));
		expect(d.ultimas).toEqual({ censo: '2026-11-16T10:00:00+00:00', ech: null, siniestros: null });
		expect(d).not.toHaveProperty('historial');
	});

	it('lo que se incrusta en /fuentes no crece con el historial', () => {
		const largo = Array.from({ length: 5000 }, (_, i) => c('censo', `2025-01-01T00:00:${String(i % 60).padStart(2, '0')}+00:00`, 'sin cambios'));
		const chico = JSON.stringify(datosCatalogo(FUENTES, HISTORIAL)).length;
		const grande = JSON.stringify(datosCatalogo(FUENTES, [...HISTORIAL, ...largo])).length;
		expect(grande).toBe(chico);
	});
});

describe('nivelesDetallados (AC-V28)', () => {
	const fu = (niveles: string[]) => ({ niveles_publicados: niveles }) as unknown as Fuente;
	it('el nivel más fino de alcance nacional y, si es más fino, el de Montevideo', () => {
		expect(nivelesDetallados(fu(['pais', 'departamento', 'municipio_mvd']))).toBe('Departamento · Municipio (solo Montevideo)');
		expect(nivelesDetallados(fu(['departamento', 'seccion', 'segmento', 'localidad', 'barrio_mvd', 'ccz_mvd']))).toBe('Segmento censal');
		expect(nivelesDetallados(fu(['departamento']))).toBe('Departamento');
		expect(nivelesDetallados(fu(['pais']))).toBe('País');
		// de Montevideo, solo el más fino
		expect(nivelesDetallados(fu(['departamento', 'municipio_mvd', 'ccz_mvd']))).toBe('Departamento · CCZ (solo Montevideo)');
	});
});
