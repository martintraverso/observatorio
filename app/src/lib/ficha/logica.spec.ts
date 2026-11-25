import { describe, expect, it } from 'vitest';
import type { Ficha, Observacion } from '../datos';
import {
	cita,
	consultaMapa,
	CORTE_SIN_MOTIVO,
	cuadrosEducacion,
	datosEnPadre,
	datosEnRegion,
	indicadorIngreso,
	INGRESO_POR_DEFECTO,
	serieIngreso,
	decimalesComunes,
	densidad,
	fuentesDeFicha,
	geometriaMiniSerie,
	indicesEtiquetas,
	marcasRedondas,
	notaNoAditiva,
	observacionesDeSeccion,
	ordenSerieEducacion,
	partes,
	puntosSerie,
	rutaLegible,
	SECCIONES_FICHA,
	separarSeries,
	textoEnPadre
} from './logica';

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

describe('fuentesDeFicha (AC-V18)', () => {
	const cap = (id: string, fuente_id: string, fecha_proceso: string, archivo = `${id}.html`) => ({ id, fuente_id, archivo, sha256: 'x'.repeat(64), fecha_proceso });
	const fuente = (nombre: string) => ({ nombre, organismo: 'INE', licencia: 'L', pagina: '', url_descarga: '' });

	it('una entrada por fuente, con sus capturas de la más reciente a la más vieja', () => {
		const g = fuentesDeFicha({
			capturas: {
				a: cap('a', 'ech', '2026-01-10'),
				b: cap('b', 'censo', '2025-05-01'),
				c: cap('c', 'ech', '2026-03-10'),
				d: cap('d', 'ech', '2026-02-10')
			},
			fuentes: { ech: fuente('ECH'), censo: fuente('Censo') }
		});
		expect(g.map((x) => [x.id, x.capturas.length])).toEqual([['ech', 3], ['censo', 1]]);
		expect(g[0].capturas.map((c) => c.id)).toEqual(['c', 'd', 'a']);
		expect(g[0].ultima.id).toBe('c');
		expect(g[1].fuente?.nombre).toBe('Censo');
	});

	it('sin capturas, sin entradas', () => {
		expect(fuentesDeFicha({ capturas: {}, fuentes: {} })).toEqual([]);
	});
});

describe('series de ingresos (AC-I21)', () => {
	it('por defecto, la variante titular del INE', () => {
		expect(indicadorIngreso(INGRESO_POR_DEFECTO)).toBe('ing_hogar_medio_sagu_svl');
	});
	it('cada combinación da su indicador; a precios de enero de 2005 solo sin aguinaldo ni valor locativo', () => {
		expect(indicadorIngreso({ ...INGRESO_POR_DEFECTO, medida: 'pc', aguinaldo: true, valorLocativo: true })).toBe('ing_pc_medio_cagu_cvl');
		expect(indicadorIngreso({ ...INGRESO_POR_DEFECTO, base: 'ene2005', aguinaldo: true })).toBe('ing_hogar_medio_sagu_svl_ene2005');
	});
	it('trimestres o totales anuales', () => {
		const o = (periodo: string, tipo: 'trimestre' | 'anio') => ({ ...obs('ing_hogar_medio_sagu_svl', 1), periodo, tipo_periodo: tipo });
		const series = new Map([['ing_hogar_medio_sagu_svl', [o('2025-T4', 'trimestre'), o('2025', 'anio')]]]) as never;
		expect(serieIngreso(series, INGRESO_POR_DEFECTO).map((x) => x.periodo)).toEqual(['2025-T4']);
		expect(serieIngreso(series, { ...INGRESO_POR_DEFECTO, frecuencia: 'anio' }).map((x) => x.periodo)).toEqual(['2025']);
	});
});

describe('datosEnRegion (AC-I22)', () => {
	const indicadores = {
		tasa_actividad: { codigo: 'tasa_actividad', nombre: 'Tasa de actividad', tema: 'Trabajo', unidad: '%' }
	} as never;
	const region = { id: 'INE-2023/region/interior', nivel: 'region' as const, codigo: 'interior', nombre: 'Interior del país', temas: ['Ingresos'] };
	const depto = { padres: [], indicadores, region, observaciones: [{ ...obs('tasa_actividad', 60) }] };

	it('un departamento del Interior con trabajo propio: los ingresos están en la región', () => {
		const r = datosEnRegion(depto as never, ['Trabajo', 'Ingresos']);
		expect(r?.region.nombre).toBe('Interior del país');
		expect(r?.temas).toEqual(['Ingresos']);
	});

	it('sin región, o sin datos del tema en la región, nada', () => {
		expect(datosEnRegion({ ...depto, region: undefined } as never, ['Ingresos'])).toBeNull();
		expect(datosEnRegion({ ...depto, region: { ...region, temas: [] } } as never, ['Ingresos'])).toBeNull();
	});

	it('si un nivel que la contiene ya tiene el tema, no se repite', () => {
		const padres = [{ id: 'INE-2023/departamento/01', nivel: 'departamento', codigo: '01', nombre: 'Montevideo', valores: { ing_x: { '2026-T3': 1 } } }];
		const ind = { ...(indicadores as object), ing_x: { codigo: 'ing_x', nombre: 'Ingreso', tema: 'Ingresos', unidad: 'pesos' } };
		expect(datosEnRegion({ ...depto, padres, indicadores: ind } as never, ['Ingresos'])).toBeNull();
	});
});

describe('datosEnPadre (AC-V24)', () => {
	const res = (nivel: string, codigo: string, nombre: string, valores: Record<string, Record<string, number>>) =>
		({ id: `INE-2023/${nivel}/${codigo}`, nivel, codigo, nombre, valores }) as never;
	const indicadores = {
		pob_total: { codigo: 'pob_total', nombre: 'Personas', tema: 'Población', unidad: 'personas' },
		tasa_actividad: { codigo: 'tasa_actividad', nombre: 'Tasa de actividad', tema: 'Trabajo', unidad: '%' }
	} as never;
	const padres = [
		res('departamento', '16', 'San José', { pob_total: { '2023': 1 }, tasa_actividad: { '2026-07/2026-09': 60 } }),
		res('seccion', '1601', 'Sección 01', { pob_total: { '2023': 1 } })
	];

	it('el nivel más cercano que tiene datos del tema', () => {
		const r = datosEnPadre({ padres, indicadores }, ['Trabajo', 'Ingresos']);
		expect(r?.padre.nombre).toBe('San José');
		expect(r?.temas).toEqual(['Trabajo']);
		expect(datosEnPadre({ padres, indicadores }, ['Población'])?.padre.nivel).toBe('seccion');
	});

	it('null si ningún nivel que la contiene tiene datos', () => {
		expect(datosEnPadre({ padres, indicadores }, ['Educación'])).toBeNull();
		expect(datosEnPadre({ padres: [], indicadores }, ['Trabajo'])).toBeNull();
	});

	it('#227: la educación del padre va aparte; su aviso `educacion` alcanza', () => {
		const conEdu = [{ ...(padres[0] as object), educacion: true }, padres[1]] as never;
		const r = datosEnPadre({ padres: conEdu, indicadores }, ['Educación']);
		expect(r?.padre.nombre).toBe('San José');
		expect(r?.temas).toEqual(['Educación']);
	});
});

describe('ejes de los gráficos de series (AC-V20)', () => {
	it('marcas redondas (1, 2, 2,5 o 5 × 10ⁿ) que cubren el rango', () => {
		const m = marcasRedondas(52.2, 65.7);
		expect(m).toEqual([50, 55, 60, 65, 70]);
		for (const [min, max] of [[0.3, 0.9], [12, 980], [3.1, 3.4], [1200, 1450], [52.2, 65.7]] as const) {
			const t = marcasRedondas(min, max);
			expect(t[0]).toBeLessThanOrEqual(min);
			expect(t.at(-1)).toBeGreaterThanOrEqual(max);
			expect(t.length).toBeGreaterThanOrEqual(3);
			expect(t.length).toBeLessThanOrEqual(7);
			const paso = t[1] - t[0];
			const mantisa = paso / 10 ** Math.floor(Math.log10(paso));
			expect([1, 2, 2.5, 5]).toContain(Number(mantisa.toFixed(6)));
		}
		expect(marcasRedondas(5, 5).length).toBeGreaterThanOrEqual(2); // rango vacío: igual hay eje
		expect(marcasRedondas(NaN, 3)).toEqual([0, 1]); // sin valores válidos no se cuelga
	});

	it('al menos 4 etiquetas en el eje x, la primera y la última incluidas', () => {
		expect(indicesEtiquetas(57, 5)).toEqual([0, 14, 28, 42, 56]);
		expect(indicesEtiquetas(3, 5)).toEqual([0, 1, 2]);
		expect(indicesEtiquetas(1, 5)).toEqual([0]);
	});

	it('los mismos decimales para el territorio y el país', () => {
		expect(decimalesComunes([60, 64.1])).toBe(1);
		expect(decimalesComunes([60, 61])).toBe(0);
		expect(decimalesComunes([1.25, 3])).toBe(2);
	});
});

describe('densidad (AC-V27)', () => {
	it('personas ÷ km², sin inventar si falta un dato', () => {
		expect(densidad(26271, 5144)).toBeCloseTo(5.107, 3);
		expect(densidad(null, 5144)).toBeNull();
		expect(densidad(26271, null)).toBeNull();
		expect(densidad(26271, 0)).toBeNull();
	});
});

describe('F4.7b1: educación en la ficha (AC-E27, AC-E28, AC-E29)', () => {
	const ind = (codigo: string, cuadro: string, columna: string, extra: Record<string, unknown> = {}) => ({
		codigo,
		nombre: `Estudiantes matriculados en educación primaria común según departamento: ${columna}`,
		unidad: 'estudiantes',
		tema: 'Educación',
		columna_origen: `Cuadro ${cuadro} · ${columna}`,
		fuente_id: 'mec_anuario_educacion',
		nota: 'Fuente: DIEE.',
		cuadro,
		...extra
	});
	const o = (indicador: string, periodo: string, valor: number, captura = 'c24') =>
		({ indicador, periodo, valor, captura_id: captura, tipo_periodo: 'anio', es_estimado: false }) as never;
	const f = {
		capturas: { c24: { archivo: 'mec_anuario/2024.xlsx' }, c23: { archivo: 'mec_anuario/2023.xlsx' } },
		indicadores: {
			a_total: ind('a_total', 'II-2.2.1', 'TOTAL'),
			a_pub: ind('a_pub', 'II-2.2.1', 'FORMA DE ADMINISTRACIÓN/PÚBLICA/TOTAL'),
			b_prom: ind('b_prom', 'II-2.2.13', 'RENDIMIENTO ESCOLAR/PROMOVIDOS/TOTAL'),
			edu_ii_2_2_13_rendimiento_escolar_tasa_promocion_total: ind('edu_ii_2_2_13_rendimiento_escolar_tasa_promocion_total', 'II-2.2.13', '', {
				nombre: 'Tasa de promoción (II-2.2.13): total',
				columna_origen: 'Cuadro II-2.2.13 (calculado)',
				unidad: '%',
				es_derivado: true
			}),
			c_doc: ind('c_doc', 'II-2.3.1', 'TOTAL', { unidad: 'docentes' }),
			pob: { codigo: 'pob', nombre: 'Personas', unidad: 'personas', tema: 'Población', columna_origen: '', fuente_id: 'ine', nota: '' }
		},
		observaciones: [o('a_total', '2023', 90, 'c23'), o('a_total', '2024', 100), o('a_pub', '2024', 70), o('b_prom', '2024', 80), o('edu_ii_2_2_13_rendimiento_escolar_tasa_promocion_total', '2024', 95.5), o('c_doc', '2024', 7), o('pob', '2023', 1)]
	} as never;

	it('agrupa por nivel educativo, grupo y cuadro, con el total del último año y las aperturas plegadas', () => {
		const r = cuadrosEducacion(f);
		expect(r.map((n) => n.nivel)).toEqual(['Primaria']);
		expect(r[0].grupos.map((g) => g.grupo)).toEqual(['Estudiantes', 'Docentes']);
		const [matricula, rendimiento] = r[0].grupos[0].cuadros;
		expect(matricula.cuadro).toBe('II-2.2.1');
		expect(matricula.titulo).toBe('Estudiantes matriculados en educación primaria común');
		expect(matricula.anio).toBe('2024');
		expect(matricula.principal?.observacion.valor).toBe(100);
		expect(matricula.aperturas.map((a) => a.etiqueta)).toEqual(['Forma de administración · Pública · Total']);
		expect(matricula.nota).toBe('Fuente: DIEE.');
		// AC-E29: la fuente con el año del anuario y el cuadro
		expect(matricula.fuente).toBe('Fuente: MEC, Anuario Estadístico de Educación 2024, cuadro II-2.2.1');
		// en rendimiento, el resumen es la tasa calculada, marcada como tal
		expect(rendimiento.principal?.observacion.valor).toBe(95.5);
		expect(rendimiento.principal?.calculado).toBe(true);
		expect(rendimiento.principal?.unidad).toBe('%');
	});

	it('la apertura se lee sin mayúsculas sostenidas ni barras, sin cambiar sus palabras', () => {
		expect(rutaLegible('FORMA DE ADMINISTRACIÓN/PRIVADA/SEXO/M')).toBe('Forma de administración · Privada · Sexo · M');
		expect(rutaLegible('TIPO DE CURSO/Articulación/RENDIMIENTO/Promovido')).toBe('Tipo de curso · Articulación · Rendimiento · Promovido');
	});

	it('el resumen es solo el total: la tasa total aunque haya tasas de subconjuntos, o el total de una dimensión', () => {
		const tasa = (codigo: string, prom: string) =>
			ind(codigo, 'II-4.2.14', '', { nombre: 'Tasa de promoción (II-4.2.14): x', unidad: '%', es_derivado: true, formula: `${prom} / (${prom} + n) × 100` });
		const g = {
			capturas: { c24: { archivo: 'mec_anuario/2024.xlsx' } },
			indicadores: {
				p_priv: ind('p_priv', 'II-4.2.14', 'FORMA DE ADMINISTRACIÓN/PRIVADA/RENDIMIENTO/Promovido/SEXO/Mujer'),
				p_tot: ind('p_tot', 'II-4.2.14', 'TOTAL/RENDIMIENTO/Promovido/TOTAL'),
				edu_ii_4_2_14_forma_de_administracion_privada_tasa_promocion_total: tasa('edu_ii_4_2_14_forma_de_administracion_privada_tasa_promocion_total', 'p_priv'),
				edu_ii_4_2_14_total_tasa_promocion_total: tasa('edu_ii_4_2_14_total_tasa_promocion_total', 'p_tot'),
				centros_pub: ind('centros_pub', 'II-2.1.1', 'FORMA DE ADMINISTRACIÓN/PÚBLICA', { unidad: 'establecimientos' }),
				centros_tot: ind('centros_tot', 'II-2.1.1', 'FORMA DE ADMINISTRACIÓN/TOTAL', { unidad: 'establecimientos' })
			},
			observaciones: [
				o('edu_ii_4_2_14_forma_de_administracion_privada_tasa_promocion_total', '2024', 100),
				o('edu_ii_4_2_14_total_tasa_promocion_total', '2024', 86.7),
				o('centros_pub', '2024', 30),
				o('centros_tot', '2024', 37)
			]
		} as never;
		const cs = cuadrosEducacion(g).flatMap((n) => n.grupos.flatMap((x) => x.cuadros));
		const rend = cs.find((c) => c.cuadro === 'II-4.2.14')!;
		expect(rend.principal?.observacion.valor).toBe(86.7); // no la privada (100 %)
		expect(rend.principal?.etiqueta).toBe('Tasa de promoción (total)');
		// cada tasa se nombra con la apertura de su «promovidos», con la ortografía del archivo: no se repiten
		expect(rend.aperturas.map((a) => a.etiqueta)).toEqual(['Tasa de promoción · Forma de administración · Privada · Sexo · Mujer']);
		const centros = cs.find((c) => c.cuadro === 'II-2.1.1')!;
		expect(centros.principal?.observacion.valor).toBe(37); // el total publicado de su única dimensión
		expect(centros.principal?.etiqueta).toBe('Forma de administración · Total');
	});

	it('F4.7b2 (AC-E30): la serie del resumen se corta en dos tramos cuando cambia de concepto, con la nota', () => {
		const MOTIVO = 'hasta 2022 el total no incluye privados; desde 2023 sí';
		const h = {
			capturas: { c24: { archivo: 'mec_anuario/2024.xlsx' } },
			indicadores: {
				sin_priv: ind('sin_priv', 'II-3.1.1', 'TOTAL', { unidad: 'establecimientos', corte: MOTIVO }),
				con_priv: ind('con_priv', 'II-3.1.1', 'TOTAL', { unidad: 'establecimientos', corte: '' }),
				viejo: ind('viejo', 'II-2.1.1', 'TOTAL', { unidad: 'establecimientos' }),
				nuevo: ind('nuevo', 'II-2.1.1', 'TOTAL', { unidad: 'establecimientos' })
			},
			observaciones: [
				o('sin_priv', '2021', 10), o('sin_priv', '2022', 11), o('con_priv', '2023', 15), o('con_priv', '2024', 16),
				o('viejo', '2022', 30), o('nuevo', '2023', 31), o('nuevo', '2024', 32)
			]
		} as never;
		const cs = cuadrosEducacion(h).flatMap((n) => n.grupos.flatMap((x) => x.cuadros));
		const media = cs.find((c) => c.cuadro === 'II-3.1.1')!;
		expect(media.tramos.map((t) => t.map((p) => `${p.anio}:${p.valor}`))).toEqual([['2021:10', '2022:11'], ['2023:15', '2024:16']]);
		expect(media.cortes).toEqual([MOTIVO]);
		// otro id sin motivo en el registro (p. ej. una tasa calculada de otras columnas): también se corta, con el aviso
		// general; no se supone que mida lo mismo (II-4.2.14: hasta 2023 solo pública, en 2024 pública y privada)
		const prim = cs.find((c) => c.cuadro === 'II-2.1.1')!;
		expect(prim.tramos.map((t) => t.map((p) => p.valor))).toEqual([[30], [31, 32]]);
		expect(prim.cortes).toEqual([CORTE_SIN_MOTIVO]);
	});

	it('el gráfico chico ubica cada punto por año y no une la línea sobre un año sin dato', () => {
		const g = geometriaMiniSerie([[{ anio: '2020', valor: 1 }, { anio: '2022', valor: 2 }, { anio: '2023', valor: 3 }], [{ anio: '2024', valor: 4 }]], 104, 20, 2);
		expect(g.map((t) => [t.tramo, t.puntos.map((p) => p.anio)])).toEqual([
			[0, ['2020']],
			[0, ['2022', '2023']],
			[1, ['2024']]
		]);
		// x por año: 2020 en 2, 2024 en 102, 2022 a mitad de camino
		expect(g.flatMap((t) => t.puntos.map((p) => p.cx))).toEqual([2, 52, 77, 102]);
	});

	it('F4.7b3: la serie nacional de matrícula empieza por el total del sistema, después los niveles, cada apertura tras lo que abre', () => {
		const i = (ruta: string) => ({ columna_origen: `Hoja MATRÍCULA DEL SISTEMA · ${ruta}` });
		const ind = {
			cenfores: i('CENFORES - INAU'),
			total: i('TOTAL SISTEMA'),
			prim_pub: i('Total Educación Primaria/Común Pública'),
			prim: i('Total Educación Primaria'),
			ini: i('Total Edu. en la Primera Infancia e Inicial')
		};
		expect(ordenSerieEducacion(Object.keys(ind), ind)).toEqual(['total', 'ini', 'prim', 'prim_pub', 'cenfores']);
	});

	it('las siglas quedan en mayúsculas', () => {
		expect(rutaLegible('DGES/TOTAL')).toBe('DGES · Total');
	});

	it('AC-E28: las fichas más chicas dicen «Educación: datos por departamento»', () => {
		expect(textoEnPadre(['Educación'], 'departamento')).toBe('Educación: datos por departamento');
		expect(textoEnPadre(['Trabajo'], 'departamento')).toBe('Trabajo: se publica por departamento');
	});
});
