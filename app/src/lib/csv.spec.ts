import { describe, expect, it } from 'vitest';
import { COLUMNAS_CSV, csvDeFicha, nombreArchivoCsv } from './csv';
import type { Ficha } from './datos';

const FICHA = {
	id: 'INE-2023/departamento/16',
	nivel: 'departamento',
	codigo: '16',
	nombre: 'San José',
	observaciones: [
		{ indicador: 'pob_total', periodo: '2023', periodo_inicio: '2023-01-01', periodo_fin: '2023-01-01', tipo_periodo: 'censo', valor: 119715, es_estimado: false, captura_id: 'c1' },
		{ indicador: 'viviendas_total', periodo: '2026-07/2026-09', periodo_inicio: '2026-07-01', periodo_fin: '2026-09-30', tipo_periodo: 'trimestre_movil', valor: 52000.5, es_estimado: true, captura_id: 'c1' }
	],
	indicadores: {
		pob_total: { codigo: 'pob_total', nombre: 'Personas', unidad: 'personas' },
		viviendas_total: { codigo: 'viviendas_total', nombre: 'Viviendas', unidad: 'viviendas' }
	},
	capturas: { c1: { id: 'c1', fuente_id: 'f', archivo: 'Unidades, "INE".zip', sha256: 'abc', fecha_proceso: '' } },
	fuentes: { f: { nombre: 'Unidades geoestadísticas', organismo: 'INE' } }
} as unknown as Ficha;

describe('AC-F5 y AC-L27: CSV de la ficha', () => {
	const lineas = csvDeFicha(FICHA).trimEnd().split('\r\n');

	it('tiene exactamente las columnas pedidas', () => {
		expect(lineas[0]).toBe(COLUMNAS_CSV.join(','));
		expect(COLUMNAS_CSV).toEqual([
			'territorio_id', 'nivel', 'codigo', 'nombre', 'indicador', 'periodo', 'periodo_inicio', 'periodo_fin',
			'tipo_periodo', 'valor', 'unidad', 'es_estimado', 'fuente', 'archivo_origen', 'sha256', 'cuadro', 'es_derivado'
		]);
	});

	it('una fila por valor mostrado, con su origen y escapando comillas y comas', () => {
		expect(lineas).toHaveLength(3);
		expect(lineas[1]).toBe(
			'INE-2023/departamento/16,departamento,16,San José,pob_total,2023,2023-01-01,2023-01-01,censo,119715,personas,false,INE · Unidades geoestadísticas,"Unidades, ""INE"".zip",abc,,false'
		);
		expect(lineas[2]).toContain(',2026-07/2026-09,2026-07-01,2026-09-30,trimestre_movil,52000.5,viviendas,true,'); // AC-L27
		expect(nombreArchivoCsv(FICHA)).toBe('observatorio_departamento_16.csv');
	});
});

describe('AC-I25: los ingresos en el CSV de la ficha', () => {
	it('cada fila trae tipo y fechas del período y la base de precios en la unidad', async () => {
		const { readFileSync } = await import('node:fs');
		const f = JSON.parse(readFileSync('e2e/fixtures/ficha-region-interior-ingresos.json', 'utf-8')) as Ficha;
		const [cabecera, ...filas] = csvDeFicha(f).trim().split('\r\n').map((l) => l.split(','));
		const col = (n: string) => cabecera.indexOf(n);
		const t3 = filas.find((r) => r[col('indicador')] === 'ing_hogar_medio_sagu_svl' && r[col('periodo')] === '2026-T3')!;
		expect([t3[col('tipo_periodo')], t3[col('periodo_inicio')], t3[col('periodo_fin')]]).toEqual(['trimestre', '2026-07-01', '2026-09-30']);
		expect(t3[col('unidad')]).toBe('pesos corrientes por mes');
		const anual = filas.find((r) => r[col('indicador')] === 'ing_hogar_medio_sagu_svl_ene2005' && r[col('tipo_periodo')] === 'anio')!;
		expect(anual[col('unidad')]).toBe('pesos de enero de 2005 por mes');
		expect([anual[col('periodo_inicio')].slice(5), anual[col('periodo_fin')].slice(5)]).toEqual(['01-01', '12-31']);
	});
});

describe('AC-E31: la educación en el CSV de la ficha', () => {
	it('cada fila trae el cuadro de origen y si es un valor calculado', () => {
		const ficha = {
			...FICHA,
			observaciones: [
				{ indicador: 'edu_ii_2_2_1_total', periodo: '2024', periodo_inicio: '2024-01-01', periodo_fin: '2024-12-31', tipo_periodo: 'anio', valor: 10094, es_estimado: false, captura_id: 'c1' },
				{ indicador: 'edu_tasa', periodo: '2024', periodo_inicio: '2024-01-01', periodo_fin: '2024-12-31', tipo_periodo: 'anio', valor: 97.97, es_estimado: false, captura_id: 'c1' }
			],
			indicadores: {
				edu_ii_2_2_1_total: { codigo: 'edu_ii_2_2_1_total', unidad: 'estudiantes', cuadro: 'II-2.2.1', es_derivado: false },
				edu_tasa: { codigo: 'edu_tasa', unidad: '%', cuadro: 'II-2.2.13', es_derivado: true }
			}
		} as unknown as Ficha;
		const lineas = csvDeFicha(ficha).trimEnd().split('\r\n');
		expect(lineas[1]).toMatch(/,2024,2024-01-01,2024-12-31,anio,10094,estudiantes,false,.*,II-2\.2\.1,false$/);
		expect(lineas[2]).toMatch(/,97\.97,%,false,.*,II-2\.2\.13,true$/);
	});
});
