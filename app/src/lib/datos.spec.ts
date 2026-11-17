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
		expect(NIVELES).toHaveLength(7);
	});

	it('leerJson usa el fetch recibido y falla con ErrorDatos si no hay archivo', async () => {
		const ok = vi.fn(async () => new Response('{"a":1}', { status: 200 }));
		await expect(leerJson('x.json', ok as unknown as typeof fetch)).resolves.toEqual({ a: 1 });
		expect(ok).toHaveBeenCalledWith('/observatorio/datos-web/x.json');

		const no = vi.fn(async () => new Response('', { status: 404 }));
		await expect(leerJson('falta.json', no as unknown as typeof fetch)).rejects.toBeInstanceOf(ErrorDatos);
	});
});
