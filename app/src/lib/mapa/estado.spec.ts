import { describe, expect, it } from 'vitest';
import {
	avisoSinMapa,
	filasComparacion,
	clase,
	clasesCuantiles,
	encuadreNivel,
	estadoDesdeUrl,
	formaSelectorNivel,
	etiquetaPeriodo,
	etiquetasLeyenda,
	fuenteCorta,
	fuenteYPeriodo,
	gruposDelTema,
	indicadorInicialDelTema,
	indicadoresDelGrupo,
	indicadoresDelTema,
	nivelAlCambiar,
	nivelesConDatos,
	nivelesDibujables,
	nivelesOfrecidos,
	nivelMasDetallado,
	opcionNivel,
	totalDelPais,
	urlDesdeEstado,
	zoomMinimo,
	type IndicadorMapa,
	territorioAlCambiarNivel,
	type NivelCatalogo
} from './estado';

const ind = (codigo: string, tema: string, niveles: IndicadorMapa['niveles'], periodos = ['2023']) =>
	({ codigo, nombre: codigo === 'pob_total' ? 'Personas' : 'Desempleo', unidad: 'personas', tema, niveles, periodos }) as IndicadorMapa;

const PERSONAS = ind('pob_total', 'Población', ['departamento', 'seccion', 'segmento', 'localidad']);
const DESEMPLEO = ind('desempleo', 'Trabajo', ['departamento'], ['2022', '2023']);
const INDICADORES = [PERSONAS, DESEMPLEO];

/** Como niveles.json de pipeline/web.py (M11.1): orden de D2, dibujables de D1. */
const nivel = (
	id: string,
	etiqueta: string,
	orden: number,
	dibujable: boolean,
	dentro_de: string[],
	extra: Partial<NivelCatalogo> = {}
): NivelCatalogo => ({ id, etiqueta, ayuda: null, orden, dibujable, capa: dibujable, minzoom: null, ambito: 'pais', dentro_de, ...extra });
const MVD = { ayuda: 'Solo Montevideo', ambito: 'montevideo' } as const;
const CATALOGO: NivelCatalogo[] = [
	nivel('pais', 'País', 0, false, []),
	nivel('region', 'Región', 1, false, ['pais']),
	nivel('departamento', 'Departamento', 2, true, ['pais']),
	nivel('municipio_mvd', 'Municipio', 3, true, ['pais', 'departamento'], MVD),
	nivel('seccion', 'Sección', 4, true, ['pais', 'departamento']),
	nivel('barrio_mvd', 'Barrio', 5, true, ['pais', 'departamento'], MVD),
	nivel('segmento', 'Segmento', 6, true, ['pais', 'departamento', 'seccion'], { minzoom: 9 }),
	nivel('localidad', 'Localidad', 7, false, ['pais', 'departamento']),
	nivel('ccz_mvd', 'CCZ', 8, false, ['pais', 'departamento'], MVD)
];

describe('AC-M2 / AC-V9 en el mapa: reemplazados por AC-N4/AC-N9 (M11.4)', () => {
	it('AC-N9: el mapa nunca llega a «no se publica por…»: solo ofrece niveles con datos y sin aviso', () => {
		for (const i of INDICADORES) {
			expect(avisoSinMapa(i, CATALOGO)).toBeNull();
			for (const n of nivelesOfrecidos(i, CATALOGO)) expect(i.niveles).toContain(n);
		}
	});

	it('el indicador sin ningún nivel en el mapa lo dice, sin «no se publica por…»', () => {
		const a = avisoSinMapa(ind('solo_uy', 'Trabajo', ['pais']), CATALOGO);
		expect(a).toEqual({ mensaje: '«Desempleo» se publica solo para todo el país: no hay datos por territorio para el mapa.', regional: false });
		expect(a?.mensaje).not.toContain('no se publica por');
	});

	it('AC-N6: lista con 2 o más niveles, texto fijo con 1, oculto con 0', () => {
		expect(formaSelectorNivel(['departamento', 'municipio_mvd'])).toBe('lista');
		expect(formaSelectorNivel(['departamento'])).toBe('texto');
		expect(formaSelectorNivel([])).toBe('oculto');
	});

	it('nivel más detallado', () => {
		expect(nivelMasDetallado(PERSONAS, CATALOGO)).toBe('segmento');
		expect(nivelMasDetallado(DESEMPLEO, CATALOGO)).toBe('departamento');
		expect(nivelMasDetallado(ind('x', 'Trabajo', ['localidad']), CATALOGO)).toBeNull();
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
		const e = { indicador: 'pob_total', nivel: 'seccion', periodo: '2023', territorio: 'seccion/1605' };
		expect(estadoDesdeUrl(new URLSearchParams(urlDesdeEstado(e)), INDICADORES, CATALOGO)).toEqual(e);
	});

	it('valores por defecto y valores inválidos', () => {
		expect(estadoDesdeUrl(new URLSearchParams(''), INDICADORES, CATALOGO)).toEqual({
			indicador: 'pob_total',
			nivel: 'departamento',
			periodo: '2023',
			territorio: null
		});
		const raro = estadoDesdeUrl(new URLSearchParams('indicador=x&nivel=zona&periodo=1900&territorio=../x'), INDICADORES, CATALOGO);
		expect(raro).toEqual({ indicador: 'pob_total', nivel: 'departamento', periodo: '2023', territorio: null });
	});
});

describe('F2.8b: Trabajo en el mapa', () => {
	const ACTIVIDAD = ind('tasa_actividad', 'Trabajo', ['pais', 'departamento', 'municipio_mvd'], ['2021-12/2022-02', '2026-07/2026-09']);

	it('AC-L23: el nivel municipio de Montevideo está en el mapa; Trabajo ofrece Departamento y Municipio, sin aviso (AC-N9)', () => {
		expect(nivelesDibujables(CATALOGO).map((n) => n.id)).toContain('municipio_mvd');
		expect(nivelesOfrecidos(ACTIVIDAD, CATALOGO)).toEqual(['departamento', 'municipio_mvd']);
		expect(avisoSinMapa(ACTIVIDAD, CATALOGO)).toBeNull();
		expect(nivelMasDetallado(ind('pob_total', 'Población', ['departamento', 'seccion'], ['2023']), CATALOGO)).toBe('seccion');
	});

	it('AC-L24: etiqueta del trimestre móvil', () => {
		expect(etiquetaPeriodo('2026-07/2026-09')).toBe('Trimestre móvil jul–set 2026');
		expect(etiquetaPeriodo('2025-12/2026-02')).toBe('Trimestre móvil dic 2025–feb 2026');
		expect(etiquetaPeriodo('2026-T3')).toBe('jul–set 2026'); // F3.7b: trimestre calendario
		expect(etiquetaPeriodo('2016-T1')).toBe('ene–mar 2016');
		expect(etiquetaPeriodo('2023')).toBe('2023');
	});

	it('AC-V17: la fuente y el período no repiten el año', () => {
		expect(fuenteYPeriodo('INE, Unidades geoestadísticas Censo 2023', '2023')).toBe('INE, Unidades geoestadísticas Censo 2023');
		expect(fuenteYPeriodo('INE, ECH', 'Trimestre móvil jul–set 2026')).toBe('INE, ECH · Trimestre móvil jul–set 2026');
		expect(fuenteYPeriodo('INE, ECH', '2025')).toBe('INE, ECH · 2025');
		expect(fuenteYPeriodo('INE, Censo 2023', '2011')).toBe('INE, Censo 2023 · 2011');
		expect(fuenteYPeriodo('INE, Censo 12023', '2023')).toBe('INE, Censo 12023 · 2023');
	});

	it('AC-V2: el municipio se ofrece como «Municipio» con la ayuda «Solo Montevideo»', () => {
		expect(opcionNivel(CATALOGO, 'municipio_mvd')).toEqual({ etiqueta: 'Municipio', ayuda: 'Solo Montevideo' });
		expect(opcionNivel(CATALOGO, 'departamento')).toEqual({ etiqueta: 'Departamento' });
		for (const n of nivelesDibujables(CATALOGO)) expect(opcionNivel(CATALOGO, n.id).etiqueta).not.toMatch(/\(/);
	});

	it('el selector ofrece solo niveles con datos (con solo el Censo, sin municipio)', () => {
		expect(nivelesConDatos([PERSONAS], CATALOGO)).toEqual(['departamento', 'seccion', 'segmento']);
		expect(nivelesConDatos([PERSONAS, ACTIVIDAD], CATALOGO)).toEqual(['departamento', 'municipio_mvd', 'seccion', 'segmento']);
	});

	it('total del país según el período: nunca se suma', () => {
		const pais = { indicadores: { tasa_actividad: { '2026-07/2026-09': { UY: 64.1 } } } };
		expect(totalDelPais(pais, 'tasa_actividad', '2026-07/2026-09')).toBe('periodo');
		expect(totalDelPais(pais, 'tasa_actividad', '2021-12/2022-02')).toBe('otros');
		expect(totalDelPais(pais, 'pob_total', '2023')).toBe('nunca');
		expect(totalDelPais(null, 'tasa_actividad', '2026-07/2026-09')).toBe('nunca');
		expect(etiquetaPeriodo('2026-13/2027-01')).toBe('2026-13/2027-01');
	});

	it('fuente corta sin repetir la sigla («MEC, Anuario Estadístico de Educación», no «MEC, MEC»)', () => {
		expect(fuenteCorta({ organismo: 'Ministerio de Educación y Cultura (MEC)', nombre: 'Anuario Estadístico de Educación (MEC)' })).toBe(
			'MEC, Anuario Estadístico de Educación'
		);
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

describe('AC-I20: lo que se publica por región', () => {
	// Como en indicadores.json: Montevideo en «departamento», pero un solo territorio: ningún nivel en el mapa (#204).
	const ingreso = {
		codigo: 'ing_x',
		nombre: 'Ingreso',
		unidad: 'pesos',
		tema: 'Ingresos',
		niveles: ['departamento', 'pais', 'region'],
		niveles_mapa: [],
		periodos: ['2026-T3']
	} as never;
	it('avisa y no usa el coroplético, aunque Montevideo esté en el nivel departamento', () => {
		expect(nivelesOfrecidos(ingreso, CATALOGO)).toEqual([]);
		const a = avisoSinMapa(ingreso, CATALOGO);
		expect(a?.regional).toBe(true);
		expect(a?.mensaje).toBe('Los ingresos se publican por región: País · Montevideo · Interior.');
	});
	it('arma las cinco filas en orden, con null si falta un valor', () => {
		const v = {
			pais: { indicadores: { ing_x: { '2026-T3': { UY: 98653 } } } },
			departamento: { indicadores: { ing_x: { '2026-T3': { '01': 120938 } } } },
			region: { indicadores: { ing_x: { '2026-T3': { interior: 83651, 'interior-5000': 85181 } } } }
		};
		expect(filasComparacion(v, 'ing_x', '2026-T3').map((f) => [f.nombre, f.valor])).toEqual([
			['Total país', 98653],
			['Montevideo', 120938],
			['Interior', 83651],
			['Interior: localidades de 5.000 o más', 85181],
			['Interior: localidades pequeñas y rurales', null]
		]);
	});
});

describe('M11.2: niveles según el indicador elegido', () => {
	// Los niveles de cada indicador como los publica indicadores.json con la base completa (2026-11-24).
	const POBLACION = ind('pob_total', 'Población', ['barrio_mvd', 'ccz_mvd', 'departamento', 'localidad', 'seccion', 'segmento']);
	const TASA_DESEMPLEO = ind('tasa_desempleo', 'Trabajo', ['departamento', 'municipio_mvd', 'pais']);
	const MATRICULA = ind('edu_matricula', 'Educación', ['departamento', 'pais', 'region']);
	// Ingresos publica Montevideo en el nivel departamento, un solo territorio: `niveles_mapa` vacío (AC-N6, #204).
	const INGRESO = { ...ind('ing_medio', 'Ingresos', ['departamento', 'pais', 'region']), niveles_mapa: [] };
	const SOLO_PAIS = ind('solo_pais', 'Trabajo', ['pais', 'region']);
	// F5 (criminalidad): la seccional entra al catálogo entre municipio y sección (D2), sin tocar el código de la app.
	const CON_SECCIONAL = [...CATALOGO, nivel('seccional', 'Seccional', 3.5, true, ['pais', 'departamento'], { ayuda: 'Seccional policial' })];
	const HOMICIDIOS = ind('tasa_homicidios', 'Seguridad', ['departamento', 'seccional']);
	const RAPINAS = ind('tasa_rapinas', 'Seguridad', ['departamento', 'seccional', 'barrio_mvd']);

	it('AC-N4: con datos y dibujables, en el orden del catálogo; ninguno sin datos', () => {
		expect(nivelesOfrecidos(POBLACION, CATALOGO)).toEqual(['departamento', 'seccion', 'barrio_mvd', 'segmento']);
		for (const i of [POBLACION, TASA_DESEMPLEO, MATRICULA, INGRESO, SOLO_PAIS]) {
			for (const n of nivelesOfrecidos(i, CATALOGO)) expect(i.niveles).toContain(n);
		}
		expect(nivelesOfrecidos(undefined, CATALOGO)).toEqual([]);
	});

	it('AC-N5: la tabla de niveles por indicador (D1: localidad y CCZ no van al mapa)', () => {
		const tabla = (i: IndicadorMapa, cat = CATALOGO) => nivelesOfrecidos(i, cat).map((n) => opcionNivel(cat, n).etiqueta).join(' · ');
		expect(tabla(POBLACION)).toBe('Departamento · Sección · Barrio · Segmento');
		expect(tabla(TASA_DESEMPLEO)).toBe('Departamento · Municipio');
		expect(tabla(MATRICULA)).toBe('Departamento');
		expect(tabla(INGRESO)).toBe('');
		expect(tabla({ ...MATRICULA, niveles_mapa: ['departamento', 'pais', 'region'] })).toBe('Departamento'); // 19 departamentos
		expect(tabla(SOLO_PAIS)).toBe('');
		expect(tabla(HOMICIDIOS, CON_SECCIONAL)).toBe('Departamento · Seccional');
		expect(tabla(RAPINAS, CON_SECCIONAL)).toBe('Departamento · Seccional · Barrio');
	});

	it('AC-N3: país y región nunca se ofrecen', () => {
		expect(nivelesOfrecidos(ind('x', 'Trabajo', ['pais', 'region']), CATALOGO)).toEqual([]);
	});

	it('AC-N7: se conserva el nivel si se ofrece; si no, el más cercano que lo contiene; si no, el más grueso', () => {
		const al = (actual: string, i: IndicadorMapa, cat = CATALOGO) => nivelAlCambiar(actual, nivelesOfrecidos(i, cat), cat);
		expect(al('segmento', TASA_DESEMPLEO)).toBe('departamento'); // Personas / Segmento → Trabajo
		expect(al('municipio_mvd', POBLACION)).toBe('departamento'); // Trabajo / Municipio → Personas
		expect(al('barrio_mvd', HOMICIDIOS, CON_SECCIONAL)).toBe('departamento'); // la seccional no contiene al barrio (#202)
		expect(al('seccion', POBLACION)).toBe('seccion'); // se conserva
		expect(al('segmento', ind('x', 'Población', ['seccion', 'departamento']))).toBe('seccion'); // el más cercano que lo contiene
		expect(al('departamento', ind('x', 'Población', ['seccion', 'segmento']))).toBe('seccion'); // nada lo contiene: el más grueso
		expect(al('departamento', SOLO_PAIS)).toBeNull();
	});

	it('AC-N8: un enlace con un nivel que el indicador no ofrece abre con la regla de AC-N7', () => {
		const url = (q: string) => estadoDesdeUrl(new URLSearchParams(q), [POBLACION, TASA_DESEMPLEO, INGRESO, SOLO_PAIS], CATALOGO);
		expect(url('indicador=tasa_desempleo&nivel=seccion&periodo=2023').nivel).toBe('departamento');
		expect(url('indicador=pob_total&nivel=municipio_mvd&periodo=2023').nivel).toBe('departamento');
		expect(url('indicador=pob_total&nivel=barrio_mvd&periodo=2023').nivel).toBe('barrio_mvd');
		expect(url('indicador=ing_medio&nivel=seccion&periodo=2023').nivel).toBe('seccion'); // sin niveles en el mapa: queda el pedido
		// sin niveles dibujables: queda un nivel del mapa
		expect(url('indicador=solo_pais&nivel=seccion&periodo=2023').nivel).toBe('seccion');
		expect(url('indicador=solo_pais&nivel=pais&periodo=2023').nivel).toBe('departamento');
		// AC-V8: el territorio sigue al nivel corregido; nunca queda uno de otro nivel en el panel
		const t = (q: string) => url(q).territorio;
		expect(t('indicador=pob_total&nivel=municipio_mvd&periodo=2023&territorio=municipio_mvd/A')).toBe('departamento/01');
		expect(t('indicador=tasa_desempleo&nivel=segmento&periodo=2023&territorio=segmento/0710101')).toBe('departamento/07');
		expect(t('indicador=tasa_desempleo&nivel=seccion&periodo=2023&territorio=seccion/1605')).toBe('departamento/16');
		expect(t('indicador=tasa_desempleo&nivel=localidad&periodo=2023&territorio=localidad/0710')).toBeNull(); // el padre no se sabe por el código: se vacía
		expect(t('indicador=pob_total&nivel=seccion&periodo=2023&territorio=seccion/1605')).toBe('seccion/1605'); // nivel válido: no se toca
	});

	it('AC-N13: un nivel nuevo del catálogo aparece sin cambiar el código', () => {
		const cat = [...CATALOGO, nivel('nivel_falso', 'Nivel falso', 4.5, true, ['departamento'], { minzoom: 11 })];
		const i = ind('x', 'Población', ['departamento', 'nivel_falso']);
		expect(nivelesOfrecidos(i, cat)).toEqual(['departamento', 'nivel_falso']);
		expect(zoomMinimo(cat, 'nivel_falso')).toBe(11);
		expect(estadoDesdeUrl(new URLSearchParams('indicador=x&nivel=nivel_falso&periodo=2023'), [i], cat).nivel).toBe('nivel_falso');
	});

	it('el zoom mínimo sale del catálogo (segmentos desde 9)', () => {
		expect(zoomMinimo(CATALOGO, 'segmento')).toBe(9);
		expect(zoomMinimo(CATALOGO, 'departamento')).toBe(0);
	});
});

describe('M11.3: encuadre y selección según el catálogo', () => {
	it('AC-V7: Montevideo para los niveles solo de Montevideo, el país para el departamento, el departamento para los demás', () => {
		expect(encuadreNivel(CATALOGO, 'municipio_mvd')).toBe('montevideo');
		expect(encuadreNivel(CATALOGO, 'barrio_mvd')).toBe('montevideo');
		expect(encuadreNivel(CATALOGO, 'departamento')).toBe('pais');
		expect(encuadreNivel(CATALOGO, 'seccion')).toBe('departamento');
		expect(encuadreNivel(CATALOGO, 'segmento')).toBe('departamento');
	});

	it('AC-N13: un nivel nuevo se encuadra por su ámbito y su dentro_de, sin código nuevo', () => {
		const cat = [...CATALOGO, nivel('nacional', 'Nacional', 2.5, true, ['pais']), nivel('zona_mvd', 'Zona', 5.5, true, ['pais', 'departamento'], MVD)];
		expect(encuadreNivel(cat, 'nacional')).toBe('pais');
		expect(encuadreNivel(cat, 'zona_mvd')).toBe('montevideo');
	});

	it('AC-V8 sin la ficha: el departamento por el código o por el ámbito; si no se sabe, se vacía', () => {
		expect(territorioAlCambiarNivel('barrio_mvd/1000000', 'departamento', CATALOGO)).toBe('departamento/01');
		expect(territorioAlCambiarNivel('segmento/0710101', 'departamento', CATALOGO)).toBe('departamento/07');
		expect(territorioAlCambiarNivel('barrio_mvd/1000000', 'municipio_mvd', CATALOGO)).toBeNull(); // un barrio no está dentro de un municipio
		expect(territorioAlCambiarNivel('departamento/07', 'seccion', CATALOGO)).toBeNull(); // ir a uno más fino vacía
	});
});

describe('F4.7c2 (AC-E26): tema «Educación» en el mapa', () => {
	const tasa = (codigo: string, nombre: string, grupo: string) =>
		({ ...ind(codigo, 'Educación', ['departamento'], ['2023', '2024']), nombre, grupo, es_derivado: true }) as IndicadorMapa;
	const D3 = tasa('edu_ii_2_2_13_rendimiento_escolar_tasa_promocion_total', 'Tasa de promoción en educación primaria común pública', 'Primaria');
	const EDU = [
		tasa('edu_ii_2_2_14_x', 'Tasa de promoción en educación primaria común pública — sexo · mujer', 'Primaria'),
		D3,
		tasa('edu_ii_4_2_14_total_tasa_promocion_total', 'Tasa de promoción en educación media superior general', 'Media superior'),
		tasa('edu_ii_3_2_11_y', 'Tasa de promoción en educación media básica general — grado · primero', 'Media básica'),
		tasa('edu_ii_3_2_10_rendimiento_tasa_promocion', 'Tasa de promoción en educación técnica media básica', 'Media básica')
	];
	it('abre en la tasa de promoción en primaria pública (D3)', () => {
		expect(indicadorInicialDelTema([PERSONAS, ...EDU], 'Educación')?.codigo).toBe(D3.codigo);
		expect(indicadorInicialDelTema([PERSONAS, ...EDU], 'Población')?.codigo).toBe('pob_total');
	});
	it('ofrece los niveles educativos en el orden del sistema; los demás temas no tienen', () => {
		expect(gruposDelTema(EDU, 'Educación')).toEqual(['Primaria', 'Media básica', 'Media superior']);
		expect(gruposDelTema([PERSONAS], 'Población')).toEqual([]);
	});
	it('lista los indicadores del nivel, primero los totales', () => {
		expect(indicadoresDelGrupo(EDU, 'Educación', 'Media básica').map((i) => i.codigo)).toEqual(['edu_ii_3_2_10_rendimiento_tasa_promocion', 'edu_ii_3_2_11_y']);
		expect(indicadoresDelGrupo(EDU, 'Educación', 'Primaria')[0].codigo).toBe(D3.codigo);
		expect(indicadoresDelGrupo([PERSONAS, DESEMPLEO], 'Población', null)).toEqual([PERSONAS]);
	});
});
