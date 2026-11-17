import { describe, expect, it } from 'vitest';
import type { Ficha } from '../datos';
import { cita, consultaMapa, notaNoAditiva, observacionesDeSeccion, partes, SECCIONES_FICHA } from './logica';

const obs = (indicador: string, valor: number) => ({
	indicador,
	periodo: '2023',
	periodo_inicio: '2023-01-01',
	periodo_fin: '2023-01-01',
	tipo_periodo: 'censo' as const,
	valor,
	es_estimado: false,
	captura_id: 'c'
});
const ind = (codigo: string, nombre: string, tema: string) => ({ codigo, nombre, tema, unidad: 'personas' });
const sec = (codigo: string, pob: number) => ({
	id: `INE-2023/seccion/${codigo}`,
	nivel: 'seccion',
	codigo,
	nombre: `Sección ${codigo.slice(2)}`,
	valores: { pob_total: { '2023': pob } }
});

const DEPTO = {
	id: 'INE-2023/departamento/07',
	nivel: 'departamento',
	codigo: '07',
	nombre: 'Flores',
	padres: [],
	contenidos: { seccion: [sec('0701', 20000), sec('0702', 5738)] },
	observaciones: [obs('pob_total', 26271), obs('viviendas_total', 12497)],
	indicadores: {
		pob_total: ind('pob_total', 'Personas', 'Población'),
		viviendas_total: ind('viviendas_total', 'Viviendas', 'Vivienda')
	},
	capturas: {},
	fuentes: { f: { nombre: 'Unidades geoestadísticas Censo 2023', organismo: 'Instituto Nacional de Estadística (INE)' } }
} as unknown as Ficha;

describe('secciones por tema (AC-F7)', () => {
	it('agrupa observaciones por los temas de cada sección', () => {
		const [poblacion, vivienda, trabajo] = SECCIONES_FICHA;
		expect(observacionesDeSeccion(DEPTO, poblacion.temas).map((o) => o.indicador)).toEqual(['pob_total']);
		expect(observacionesDeSeccion(DEPTO, vivienda.temas).map((o) => o.indicador)).toEqual(['viviendas_total']);
		expect(observacionesDeSeccion(DEPTO, trabajo.temas)).toEqual([]);
	});

	it('pone los totales primero', () => {
		const f = {
			...DEPTO,
			observaciones: [obs('pob_hombres', 1), obs('pob_mujeres', 1), obs('pob_total', 2)],
			indicadores: {
				pob_hombres: ind('pob_hombres', 'Hombres', 'Población'),
				pob_mujeres: ind('pob_mujeres', 'Mujeres', 'Población'),
				pob_total: ind('pob_total', 'Personas', 'Población')
			}
		} as unknown as Ficha;
		expect(observacionesDeSeccion(f, ['Población']).map((o) => o.indicador)).toEqual(['pob_total', 'pob_hombres', 'pob_mujeres']);
	});
});

describe('AC-F4: la suma de secciones no es el total del departamento', () => {
	it('explica la diferencia con la razón del INE', () => {
		const nota = notaNoAditiva(DEPTO)!;
		expect(nota).toContain('La suma de las 2 secciones (25.738 personas)');
		expect(nota).toContain('total del departamento (26.271)');
		expect(nota).toContain('diferencia es de 533 (2,0 %)');
		expect(nota).toContain('registros administrativos');
	});

	it('no dice nada si coincide o si no es un departamento', () => {
		const igual = { ...DEPTO, contenidos: { seccion: [sec('0701', 26271)] } } as unknown as Ficha;
		expect(notaNoAditiva(igual)).toBeNull();
		expect(notaNoAditiva({ ...DEPTO, nivel: 'seccion' } as Ficha)).toBeNull();
	});
});

describe('proporción sobre los territorios que lo contienen', () => {
	it('usa valores publicados, del más cercano al más lejano', () => {
		const seg = {
			...DEPTO,
			nivel: 'segmento',
			padres: [
				{ id: 'd', nombre: 'Flores', valores: { pob_total: { '2023': 26271 } } },
				{ id: 's', nombre: 'Sección 01', valores: { pob_total: { '2023': 20000 } } }
			]
		} as unknown as Ficha;
		expect(partes(obs('pob_total', 1000), seg).map((p) => p.texto)).toEqual(['5,0 % de Sección 01', '3,8 % de Flores']);
	});
});

describe('AC-F6: cómo citar', () => {
	it('incluye observatorio, territorio, fuente original, URL y fecha de consulta', () => {
		const texto = cita(DEPTO, 'https://ejemplo.uy/territorio/departamento/07', new Date('2026-11-17T15:00:00Z'));
		expect(texto).toBe(
			'Observatorio Uruguay. «Flores» (departamento, código INE 07). Datos: Instituto Nacional de Estadística (INE), ' +
				'Unidades geoestadísticas Censo 2023. https://ejemplo.uy/territorio/departamento/07. Consultado el 17/11/2026.'
		);
	});
});

describe('enlace al mapa', () => {
	it('usa el nivel del territorio si el mapa lo tiene', () => {
		expect(consultaMapa({ nivel: 'segmento', codigo: '0701001' })).toBe(
			'?indicador=pob_total&nivel=segmento&periodo=2023&territorio=segmento/0701001'
		);
		expect(consultaMapa({ nivel: 'localidad', codigo: '07020' })).toContain('nivel=departamento');
	});
});
