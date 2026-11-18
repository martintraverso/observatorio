import { describe, expect, it } from 'vitest';
import type { Ficha, Observacion } from '../datos';
import { cita, consultaMapa, notaNoAditiva, observacionesDeSeccion, partes, puntosSerie, SECCIONES_FICHA, separarSeries } from './logica';

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

describe('F2.8c: series en la ficha (AC-L25)', () => {
	const tm = (indicador: string, fin: string, valor: number | null) => {
		const [a, m] = fin.split('-').map(Number);
		const ini = m > 2 ? `${a}-${String(m - 2).padStart(2, '0')}` : `${a - 1}-${String(m + 10).padStart(2, '0')}`;
		return { ...obs(indicador, valor ?? 0), valor, periodo: `${ini}/${fin}`, periodo_inicio: `${ini}-01`, periodo_fin: `${fin}-28`, tipo_periodo: 'trimestre_movil' as const };
	};
	const ficha = (observaciones: Observacion[]) =>
		({ observaciones, indicadores: { tasa_actividad: { nombre: 'Tasa de actividad', unidad: '%', tema: 'Trabajo' }, pob_total: { nombre: 'Personas', unidad: 'personas', tema: 'Población' } } }) as unknown as Ficha;

	it('separa valores puntuales (Censo) de series (trimestres móviles), en orden de período', () => {
		const f = ficha([tm('tasa_actividad', '2026-09', 69.1), obs('pob_total', 100), tm('tasa_actividad', '2022-02', 63.2)]);
		const { puntuales, series } = separarSeries(observacionesDeSeccion(f, ['Trabajo', 'Población']));
		expect(puntuales.map((o) => o.indicador)).toEqual(['pob_total']);
		expect([...series.keys()]).toEqual(['tasa_actividad']);
		expect(series.get('tasa_actividad')!.map((o) => o.periodo)).toEqual(['2021-12/2022-02', '2026-07/2026-09']);
	});

	it('la línea del país empieza en el primer informe que lo publica (sin sumar territorios)', () => {
		const territorio = [tm('tasa_actividad', '2022-02', 63.2), tm('tasa_actividad', '2025-02', 64.0), tm('tasa_actividad', '2026-09', 69.1)];
		const pais = ficha([tm('tasa_actividad', '2025-02', 64.5), tm('tasa_actividad', '2026-09', 64.1)]);
		const s = puntosSerie(territorio, pais, 'tasa_actividad');
		expect(s.territorio.map((p) => p.valor)).toEqual([63.2, 64.0, 69.1]);
		expect(s.pais.map((p) => [p.periodo, p.valor])).toEqual([
			['2024-12/2025-02', 64.5],
			['2026-07/2026-09', 64.1]
		]);
		expect(s.periodos).toHaveLength(3); // eje: los períodos del territorio
		expect(puntosSerie(territorio, null, 'tasa_actividad').pais).toEqual([]);
		// un período del país que el territorio no tiene no se dibuja ni se cuenta
		const conOtro = ficha([...pais.observaciones, tm('tasa_actividad', '2023-05', 60.0)]);
		expect(puntosSerie(territorio, conOtro, 'tasa_actividad').pais).toHaveLength(2);
	});
});
