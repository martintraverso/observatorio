import { defineConfig, devices } from '@playwright/test';

// Los tests e2e corren contra el build estático servido como GitHub Pages
// (scripts/servidor-pages.mjs, bajo BASE_PATH, por defecto /observatorio). Antes: BASE_PATH=/observatorio npm run build
const PUERTO = 4173;
const BASE = process.env.BASE_PATH || '/observatorio';

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
		{ name: 'movil', use: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 } } }
	],
	webServer: {
		command: `node scripts/servidor-pages.mjs build ${PUERTO}`,
		env: { BASE_PATH: BASE },
		port: PUERTO,
		reuseExistingServer: !process.env.CI
	}
});
