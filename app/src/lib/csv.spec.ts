import { describe, expect, it } from 'vitest';
import { COLUMNAS_CSV, csvDeFicha, nombreArchivoCsv } from './csv';
import type { Ficha } from './datos';

const FICHA = {
	id: 'INE-2023/departamento/16',
	nivel: 'departamento',
	codigo: '16',
	nombre: 'San José',
	observaciones: [
		{ indicador: 'pob_total', periodo: '2023', valor: 119715, es_estimado: false, captura_id: 'c1' },
		{ indicador: 'viviendas_total', periodo: '2023', valor: 52000.5, es_estimado: true, captura_id: 'c1' }
	],
	indicadores: {
		pob_total: { codigo: 'pob_total', nombre: 'Personas', unidad: 'personas' },
		viviendas_total: { codigo: 'viviendas_total', nombre: 'Viviendas', unidad: 'viviendas' }
	},
	capturas: { c1: { id: 'c1', fuente_id: 'f', archivo: 'Unidades, "INE".zip', sha256: 'abc', fecha_proceso: '' } },
	fuentes: { f: { nombre: 'Unidades geoestadísticas', organismo: 'INE' } }
} as unknown as Ficha;

describe('AC-F5: CSV de la ficha', () => {
	const lineas = csvDeFicha(FICHA).trimEnd().split('\r\n');

	it('tiene exactamente las columnas pedidas', () => {
		expect(lineas[0]).toBe(COLUMNAS_CSV.join(','));
		expect(COLUMNAS_CSV).toEqual([
			'territorio_id', 'nivel', 'codigo', 'nombre', 'indicador', 'periodo', 'valor', 'unidad',
			'es_estimado', 'fuente', 'archivo_origen', 'sha256'
		]);
	});

	it('una fila por valor mostrado, con su origen y escapando comillas y comas', () => {
		expect(lineas).toHaveLength(3);
		expect(lineas[1]).toBe(
			'INE-2023/departamento/16,departamento,16,San José,pob_total,2023,119715,personas,false,INE · Unidades geoestadísticas,"Unidades, ""INE"".zip",abc'
		);
		expect(lineas[2]).toContain(',52000.5,viviendas,true,');
		expect(nombreArchivoCsv(FICHA)).toBe('observatorio_departamento_16.csv');
	});
});
