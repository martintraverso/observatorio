import { describe, expect, it } from 'vitest';
import { crearBuscador, plegar } from './busqueda';
import type { EntradaIndice } from './datos';

const t = (nivel: EntradaIndice['nivel'], codigo: string, nombre: string, depto: string, padre_id: string | null) =>
	({ id: `INE-2023/${nivel}/${codigo}`, nivel, codigo, nombre, nombre_busqueda: plegar(nombre), depto, padre_id, bbox: [0, 0, 0, 0] }) as EntradaIndice;

const INDICE: EntradaIndice[] = [
	t('departamento', '11', 'Paysandú', '11', null),
	t('departamento', '16', 'San José', '16', null),
	t('departamento', '01', 'Montevideo', '01', null),
	t('seccion', '1605', 'Sección 05', '16', 'INE-2023/departamento/16'),
	t('segmento', '1605601', 'Segmento 601', '16', 'INE-2023/seccion/1605'),
	t('localidad', '16020', 'San José de Mayo', '16', 'INE-2023/departamento/16'),
	t('localidad', '11020', 'Paysandú', '11', 'INE-2023/departamento/11'),
	t('localidad', '16521', 'Puntas de Valdez', '16', 'INE-2023/departamento/16'),
	t('barrio_mvd', '5', 'Pocitos', '01', 'INE-2023/departamento/01'),
	t('ccz_mvd', '05', 'CCZ 5 (Municipio CH)', '01', 'INE-2023/departamento/01'),
	t('area_especial', '02-limite-contestado', 'Límite contestado (Artigas)', '02', null),
	t('pais', 'UY', 'Uruguay', '', null),
	{ ...t('region', 'interior', 'Interior del país', '', 'INE-2023/pais/UY'), bbox: null },
	{ ...t('region', 'interior-5000', 'Interior: localidades de 5.000 o más habitantes', '', 'INE-2023/pais/UY'), bbox: null }
];
const b = crearBuscador(INDICE);
const ids = (q: string) => b.buscar(q).map((r) => r.t.id);

describe('AC-I3: las regiones (sin geometría) se encuentran por nombre', () => {
	it('"interior" encuentra el Interior del país primero, con su nivel y el país', () => {
		const r = b.buscar('interior');
		expect(r.map((x) => x.t.id).slice(0, 2)).toEqual(['INE-2023/region/interior', 'INE-2023/region/interior-5000']);
		expect(r[0].contexto).toBe('Región · Uruguay');
	});
});

describe('plegar', () => {
	it('quita tildes, mayúsculas y espacios de más', () => {
		expect(plegar('  PAYSANDÚ ')).toBe('paysandu');
		expect(plegar('Río   Negro')).toBe('rio negro');
	});
});

describe('AC-S1: sugerencias desde 2 caracteres, sin tildes ni mayúsculas', () => {
	it('no sugiere con menos de 2 caracteres', () => {
		expect(b.buscar('p')).toEqual([]);
	});

	it('"paysandu" encuentra Paysandú (departamento antes que localidad)', () => {
		expect(ids('paysandu').slice(0, 2)).toEqual(['INE-2023/departamento/11', 'INE-2023/localidad/11020']);
		expect(ids('PAYSANDÚ')).toEqual(ids('paysandu'));
	});

	it('encuentra departamentos, localidades, barrios y CCZ', () => {
		expect(ids('san jose')).toEqual(['INE-2023/departamento/16', 'INE-2023/localidad/16020']);
		expect(ids('pocitos')).toEqual(['INE-2023/barrio_mvd/5']);
		expect(ids('ccz 5')).toEqual(['INE-2023/ccz_mvd/05']);
		expect(ids('valdez')).toEqual(['INE-2023/localidad/16521']); // palabra que empieza igual
	});

	it('no lista secciones y segmentos por nombre', () => {
		expect(ids('seccion')).toEqual([]);
	});

	it('busca por código: exacto primero, después los que empiezan igual', () => {
		expect(ids('16').slice(0, 1)).toEqual(['INE-2023/departamento/16']);
		expect(ids('16')).toContain('INE-2023/seccion/1605');
		expect(ids('1605601')).toEqual(['INE-2023/segmento/1605601']);
	});

	it('respeta el límite', () => {
		expect(b.buscar('16', 2)).toHaveLength(2);
	});
});

describe('AC-S2: un código INE válido lleva al territorio', () => {
	it.each([
		['16', 'INE-2023/departamento/16'],
		['1605', 'INE-2023/seccion/1605'],
		['16020', 'INE-2023/localidad/16020'],
		['1605601', 'INE-2023/segmento/1605601'],
		[' 1605 ', 'INE-2023/seccion/1605']
	])('%s', (codigo, id) => {
		expect(b.porCodigo(codigo)?.id).toBe(id);
	});

	it('códigos que no existen o con otro largo no llevan a ningún lado', () => {
		expect(b.porCodigo('99')).toBeNull();
		expect(b.porCodigo('160')).toBeNull();
		expect(b.porCodigo('san')).toBeNull();
	});
});

describe('AC-S3: los resultados muestran nivel y padre', () => {
	it('sección y segmento', () => {
		expect(b.buscar('1605')[0].contexto).toBe('Sección censal · San José');
		expect(b.buscar('1605601')[0].contexto).toBe('Segmento censal · Sección 05 · San José');
		expect(b.buscar('pocitos')[0].contexto).toBe('Barrio · Montevideo');
	});
});
