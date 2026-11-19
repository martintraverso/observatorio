import { defineConfig, devices } from '@playwright/test';
import { VISTAS } from './e2e/visual/ayudas';

// Los tests e2e corren contra el build estático servido como GitHub Pages
// (scripts/servidor-pages.mjs, bajo BASE_PATH, por defecto /observatorio). Antes: BASE_PATH=/observatorio npm run build
const PUERTO = 4173;
const BASE = process.env.BASE_PATH || '/observatorio';
// En CI siempre; en local con OBS_NAVEGADORES=todos (necesita `npx playwright install firefox webkit`).
const OTROS_NAVEGADORES = !!process.env.CI || process.env.OBS_NAVEGADORES === 'todos';
// Controles de desbordes y textos en los tres navegadores; capturas de referencia solo en Chromium.
const VISUAL = '**/visual/*.visual.ts';
const VISUAL_SIN_CAPTURAS = '**/visual/{ayudas,calidad}.visual.ts';
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
			: []),
		...VISTAS.map((v) => ({ name: `visual-${v.nombre}`, use: { ...devices['Desktop Chrome'], viewport: v }, testMatch: VISUAL })),
		...(OTROS_NAVEGADORES
			? VISTAS.flatMap((v) => [
					{ name: `visual-firefox-${v.nombre}`, use: { ...devices['Desktop Firefox'], viewport: v }, testMatch: VISUAL_SIN_CAPTURAS },
					{ name: `visual-safari-${v.nombre}`, use: { ...devices['Desktop Safari'], viewport: v }, testMatch: VISUAL_SIN_CAPTURAS }
				])
			: [])
	],
	webServer: {
		command: `node scripts/servidor-pages.mjs build ${PUERTO}`,
		env: { BASE_PATH: BASE },
		port: PUERTO,
		reuseExistingServer: !process.env.CI
	}
});
