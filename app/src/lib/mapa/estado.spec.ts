import { describe, expect, it } from 'vitest';
import {
	avisoNivel,
	clase,
	clasesCuantiles,
	estadoDesdeUrl,
	ETIQUETA_NIVEL_MAPA,
	etiquetaPeriodo,
	etiquetasLeyenda,
	fuenteCorta,
	indicadoresDelTema,
	NIVELES_MAPA,
	nivelesConDatos,
	nivelMasDetallado,
	totalDelPais,
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

describe('F2.8b: Trabajo en el mapa', () => {
	const ACTIVIDAD = ind('tasa_actividad', 'Trabajo', ['pais', 'departamento', 'municipio_mvd'], ['2021-12/2022-02', '2026-07/2026-09']);

	it('AC-L23: el nivel municipio de Montevideo está en el mapa y los demás niveles muestran el aviso de AC-M2', () => {
		expect(NIVELES_MAPA).toContain('municipio_mvd');
		expect(ETIQUETA_NIVEL_MAPA.municipio_mvd).toBe('Municipio (Montevideo)');
		expect(avisoNivel(ACTIVIDAD, 'departamento')).toBeNull();
		expect(avisoNivel(ACTIVIDAD, 'municipio_mvd')).toBeNull();
		expect(avisoNivel(ACTIVIDAD, 'seccion')?.mensaje).toContain('no se publica por sección');
		expect(avisoNivel(ACTIVIDAD, 'segmento')?.alternativa).toBe('municipio_mvd');
		expect(nivelMasDetallado(ind('pob_total', 'Población', ['departamento', 'seccion'], ['2023']))).toBe('seccion');
	});

	it('AC-L24: etiqueta del trimestre móvil', () => {
		expect(etiquetaPeriodo('2026-07/2026-09')).toBe('Trimestre móvil jul–set 2026');
		expect(etiquetaPeriodo('2025-12/2026-02')).toBe('Trimestre móvil dic 2025–feb 2026');
		expect(etiquetaPeriodo('2023')).toBe('2023');
	});

	it('el selector ofrece solo niveles con datos (con solo el Censo, sin municipio)', () => {
		expect(nivelesConDatos([PERSONAS])).toEqual(['departamento', 'seccion', 'segmento']);
		expect(nivelesConDatos([PERSONAS, ACTIVIDAD])).toEqual(['departamento', 'municipio_mvd', 'seccion', 'segmento']);
	});

	it('total del país según el período: nunca se suma', () => {
		const pais = { indicadores: { tasa_actividad: { '2026-07/2026-09': { UY: 64.1 } } } };
		expect(totalDelPais(pais, 'tasa_actividad', '2026-07/2026-09')).toBe('periodo');
		expect(totalDelPais(pais, 'tasa_actividad', '2021-12/2022-02')).toBe('otros');
		expect(totalDelPais(pais, 'pob_total', '2023')).toBe('nunca');
		expect(totalDelPais(null, 'tasa_actividad', '2026-07/2026-09')).toBe('nunca');
		expect(etiquetaPeriodo('2026-13/2027-01')).toBe('2026-13/2027-01');
	});

	it('AC-L24: fuente corta («INE, ECH»)', () => {
		expect(fuenteCorta({ organismo: 'Instituto Nacional de Estadística (INE)', nombre: 'Mercado de trabajo por área geográfica de residencia (ECH)' })).toBe('INE, ECH');
		expect(fuenteCorta({ organismo: 'Instituto Nacional de Estadística (INE)', nombre: 'Unidades geoestadísticas Censo 2023' })).toBe(
			'INE, Unidades geoestadísticas Censo 2023'
		);
	});

	it('la leyenda de una tasa con decimales no salta de a 1', () => {
		const c = clasesCuantiles([54.1, 57.6, 59.4, 61.9, 62.6, 63.4, 65.5, 66.7, 69.1]);
		const e = etiquetasLeyenda(c!);
		expect(e[0]).toMatch(/^Hasta \d+,\d$/);
		expect(e[1]).toMatch(/^\d+,\d a \d+,\d$/);
		expect(e.slice(1, -1).every((x) => /^\d+,\d a \d+,\d$/.test(x))).toBe(true);
		expect(e.at(-1)).toMatch(/^Más de \d+,\d$/);
	});
});
