import { describe, expect, it, vi } from 'vitest';

vi.mock('$app/paths', () => ({
	asset: (p: string) => `/observatorio${p}`,
	resolve: (_id: string, p: { nivel: string; codigo: string }) => `/observatorio/territorio/${p.nivel}/${p.codigo}`
}));

const { NIVELES, esNivel, hrefFicha, partesId, rutaFicha, urlDatos, leerJson, ErrorDatos } = await import('./datos');

describe('datos', () => {
	it('arma las URL de datos con el base path', () => {
		expect(urlDatos('manifest.json')).toBe('/observatorio/datos-web/manifest.json');
		expect(urlDatos('fichas/segmento/0701001.json')).toBe('/observatorio/datos-web/fichas/segmento/0701001.json');
	});

	it('rutas y ids de territorio', () => {
		expect(rutaFicha({ nivel: 'departamento', codigo: '16' })).toBe('/territorio/departamento/16');
		expect(hrefFicha({ nivel: 'segmento', codigo: '0701001' })).toBe('/observatorio/territorio/segmento/0701001');
		expect(partesId('INE-2023/seccion/0701')).toEqual({ nivel: 'seccion', codigo: '0701' });
		expect(esNivel('segmento')).toBe(true);
		expect(esNivel('zona')).toBe(false);
		expect(NIVELES).toHaveLength(10);
		expect(NIVELES.slice(0, 2)).toEqual(['pais', 'region']); // F3.2: las regiones, después del país
		expect(esNivel('region')).toBe(true);
		expect(esNivel('pais') && esNivel('municipio_mvd')).toBe(true);
		expect(partesId('INE-2023/municipio_mvd/CH')).toEqual({ nivel: 'municipio_mvd', codigo: 'CH' });
	});

	it('leerJson usa el fetch recibido y falla con ErrorDatos si no hay archivo', async () => {
		const ok = vi.fn(async () => new Response('{"a":1}', { status: 200 }));
		await expect(leerJson('x.json', ok as unknown as typeof fetch)).resolves.toEqual({ a: 1 });
		expect(ok).toHaveBeenCalledWith('/observatorio/datos-web/x.json');

		const no = vi.fn(async () => new Response('', { status: 404 }));
		await expect(leerJson('falta.json', no as unknown as typeof fetch)).rejects.toBeInstanceOf(ErrorDatos);
	});
});

describe('unirEducacion (#227)', () => {
	it('la ficha principal más su educación dan la ficha completa; sin parte, la misma ficha', async () => {
		const { unirEducacion } = await import('./datos.ts');
		const o = (indicador: string, captura_id: string) => ({ indicador, periodo: '2024', captura_id }) as never;
		const f = {
			id: 'INE-2023/departamento/07',
			observaciones: [o('pob_total', 'c1')],
			indicadores: { pob_total: { tema: 'Población' } },
			capturas: { c1: { fuente_id: 'ine' } },
			fuentes: { ine: { nombre: 'INE' } },
			educacion: true
		} as never;
		const parte = {
			observaciones: [o('edu_x', 'c2')],
			indicadores: { edu_x: { tema: 'Educación' } },
			capturas: { c2: { fuente_id: 'mec' } },
			fuentes: { mec: { nombre: 'MEC' } }
		} as never;
		const u = unirEducacion(f, parte);
		expect(u.observaciones.map((x) => x.indicador)).toEqual(['pob_total', 'edu_x']);
		expect(Object.keys(u.indicadores)).toEqual(['pob_total', 'edu_x']);
		expect(Object.keys(u.capturas)).toEqual(['c1', 'c2']);
		expect(Object.keys(u.fuentes)).toEqual(['ine', 'mec']);
		expect(u.educacion).toBe(false); // nada pendiente
		expect(unirEducacion(f, null)).toBe(f);
	});
});
