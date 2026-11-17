import { describe, expect, it } from 'vitest';
import {
	avisoNivel,
	clase,
	clasesCuantiles,
	estadoDesdeUrl,
	etiquetasLeyenda,
	indicadoresDelTema,
	nivelMasDetallado,
	urlDesdeEstado,
	type IndicadorMapa
} from './estado';

const ind = (codigo: string, tema: string, niveles: IndicadorMapa['niveles'], periodos = ['2023']) =>
	({ codigo, nombre: codigo === 'pob_total' ? 'Personas' : 'Desempleo', unidad: 'personas', tema, niveles, periodos }) as IndicadorMapa;

const PERSONAS = ind('pob_total', 'Población', ['departamento', 'seccion', 'segmento', 'localidad']);
const DESEMPLEO = ind('desempleo', 'Trabajo', ['departamento'], ['2022', '2023']);
const INDICADORES = [PERSONAS, DESEMPLEO];

describe('AC-M2: indicador no publicado en el nivel elegido', () => {
	it('sin aviso si hay datos en ese nivel', () => {
		expect(avisoNivel(PERSONAS, 'segmento')).toBeNull();
	});

	it('avisa y nombra el nivel más detallado con datos', () => {
		const a = avisoNivel(DESEMPLEO, 'seccion');
		expect(a?.alternativa).toBe('departamento');
		expect(a?.mensaje).toBe('«Desempleo» no se publica por sección. El nivel más detallado con datos es departamento.');
	});

	it('nivel más detallado', () => {
		expect(nivelMasDetallado(PERSONAS)).toBe('segmento');
		expect(nivelMasDetallado(DESEMPLEO)).toBe('departamento');
		expect(nivelMasDetallado(ind('x', 'Trabajo', ['localidad']))).toBeNull();
	});

	it('agrupa por tema', () => {
		expect(indicadoresDelTema(INDICADORES, 'Trabajo')).toEqual([DESEMPLEO]);
		expect(indicadoresDelTema(INDICADORES, 'Educación')).toEqual([]);
	});
});

describe('clases por cuantiles y leyenda es-UY', () => {
	it('5 clases con cortes crecientes', () => {
		const v = Array.from({ length: 100 }, (_, i) => (i + 1) * 100);
		const c = clasesCuantiles(v)!;
		expect(c.cortes).toEqual([2100, 4100, 6100, 8100]);
		expect([clase(100, c), clase(2100, c), clase(2101, c), clase(10000, c)]).toEqual([0, 0, 1, 4]);
		expect(etiquetasLeyenda(c)).toEqual(['Hasta 2.100', '2.101 a 4.100', '4.101 a 6.100', '6.101 a 8.100', 'Más de 8.100']);
	});

	it('menos clases si hay pocos valores distintos', () => {
		const c = clasesCuantiles([0, 0, 0, 0, 5])!;
		expect(c.cortes.length).toBeLessThan(4);
		expect(etiquetasLeyenda(clasesCuantiles([7, 7])!)).toEqual(['7']);
		expect(clasesCuantiles([])).toBeNull();
	});
});

describe('AC-M5: estado en la URL', () => {
	it('ida y vuelta', () => {
		const e = { indicador: 'desempleo', nivel: 'seccion' as const, periodo: '2022', territorio: 'seccion/1605' };
		expect(estadoDesdeUrl(new URLSearchParams(urlDesdeEstado(e)), INDICADORES)).toEqual(e);
	});

	it('valores por defecto y valores inválidos', () => {
		expect(estadoDesdeUrl(new URLSearchParams(''), INDICADORES)).toEqual({
			indicador: 'pob_total',
			nivel: 'departamento',
			periodo: '2023',
			territorio: null
		});
		const raro = estadoDesdeUrl(new URLSearchParams('indicador=x&nivel=zona&periodo=1900&territorio=../x'), INDICADORES);
		expect(raro).toEqual({ indicador: 'pob_total', nivel: 'departamento', periodo: '2023', territorio: null });
	});
});
