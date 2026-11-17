import { defineConfig, devices } from '@playwright/test';

// Los tests e2e corren contra el build estático servido como GitHub Pages
// (scripts/servidor-pages.mjs, bajo BASE_PATH, por defecto /observatorio). Antes: BASE_PATH=/observatorio npm run build
const PUERTO = 4173;
const BASE = process.env.BASE_PATH || '/observatorio';
// En CI siempre; en local con OBS_NAVEGADORES=todos (necesita `npx playwright install firefox webkit`).
const OTROS_NAVEGADORES = !!process.env.CI || process.env.OBS_NAVEGADORES === 'todos';
const SIN_MAPA = ['**/humo.e2e.ts', '**/busqueda.e2e.ts', '**/fichas.e2e.ts', '**/fuentes-datos.e2e.ts'];

export default defineConfig({
	testDir: 'e2e',
	testMatch: '**/*.e2e.ts',
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	reporter: process.env.CI ? [['github'], ['list']] : 'list',
	use: {
		baseURL: `http://localhost:${PUERTO}${BASE}/`,
		locale: 'es-UY',
		trace: 'retain-on-failure'
	},
	projects: [
		{ name: 'escritorio', use: { ...devices['Desktop Chrome'] } },
		{ name: 'movil', use: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 } } },
		// AC-G4: Firefox y Safari (WebKit). Solo las pruebas que no dependen de dibujar el mapa: en modo
		// headless estos navegadores no tienen WebGL2 (el mapa muestra su aviso, que también se prueba).
		...(OTROS_NAVEGADORES
			? [
					{ name: 'firefox', use: { ...devices['Desktop Firefox'] }, testMatch: SIN_MAPA },
					{ name: 'safari', use: { ...devices['Desktop Safari'] }, testMatch: SIN_MAPA },
					{ name: 'safari-movil', use: { ...devices['iPhone 13'], viewport: { width: 390, height: 844 } }, testMatch: SIN_MAPA }
				]
			: [])
	],
	webServer: {
		command: `node scripts/servidor-pages.mjs build ${PUERTO}`,
		env: { BASE_PATH: BASE },
		port: PUERTO,
		reuseExistingServer: !process.env.CI
	}
});
