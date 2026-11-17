import { expect, test } from '@playwright/test';

// Equipos sin WebGL2: el mapa no se puede dibujar, pero la página lo dice y no se rompe.
test.use({ launchOptions: { args: ['--disable-gpu', '--disable-software-rasterizer', '--disable-webgl', '--disable-webgl2'] } });

test('sin WebGL2 el mapa avisa y el resto de la página funciona', async ({ page }) => {
	const errores: string[] = [];
	page.on('pageerror', (e) => errores.push(e.message));
	await page.goto('?indicador=pob_total&nivel=departamento&periodo=2023&territorio=departamento/07');
	const activar = page.getByRole('button', { name: 'Ver el mapa interactivo' });
	if (await activar.isVisible()) await activar.click(); // en móvil el mapa arranca al tocarlo
	await expect(page.getByText('Este navegador no puede dibujar el mapa (necesita WebGL2).')).toBeVisible();
	await expect(page.getByRole('complementary', { name: 'Territorio seleccionado' })).toContainText('Flores');
	expect(errores).toEqual([]);
});
