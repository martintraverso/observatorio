// AC-G6: Lighthouse (perfil móvil) sobre el inicio del sitio armado; falla si el rendimiento < 80.
//
// Uso: node scripts/lighthouse.mjs [url=http://localhost:4173/observatorio/] [corridas=3]
// Sirve el build con scripts/servidor-pages.mjs antes (o pasar otra URL). Usa el Chromium de Playwright,
// con WebGL por software para que el mapa también se pueda dibujar.
// Escribe lighthouse-resumen.json y, en GitHub Actions, el resumen de la corrida.
import { spawn } from 'node:child_process';
import { appendFileSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium } from '@playwright/test';
import lighthouse from 'lighthouse';

/** Lanza Chromium con depuración remota y devuelve { port, kill }. (Sin chrome-launcher: en WSL arma
 *  rutas de Windows aunque el Chrome sea de Linux.) */
function lanzarChrome(perfil) {
	const proceso = spawn(process.env.CHROME_PATH || chromium.executablePath(), [
		'--headless=new',
		'--no-sandbox',
		'--enable-unsafe-swiftshader',
		'--use-angle=swiftshader',
		'--remote-debugging-port=0',
		`--user-data-dir=${perfil}`,
		'about:blank'
	]);
	return new Promise((resolver, rechazar) => {
		let salida = '';
		proceso.stderr.on('data', (d) => {
			salida += d;
			const m = /DevTools listening on ws:\/\/[^:]+:(\d+)\//.exec(salida);
			if (m)
				resolver({
					port: Number(m[1]),
					// Espera a que Chromium termine: si se borra el perfil antes, todavía está escribiendo.
					kill: () =>
						new Promise((listo) => {
							if (proceso.exitCode !== null) return listo();
							proceso.once('exit', () => listo());
							proceso.kill();
						})
				});
		});
		proceso.once('exit', (codigo) => rechazar(new Error(`Chromium terminó (${codigo}):\n${salida}`)));
	});
}

const url = process.argv[2] ?? 'http://localhost:4173/observatorio/';
const corridas = Number(process.argv[3] ?? 3);
const MINIMO = 0.8;

const resultados = [];
for (let i = 0; i < corridas; i++) {
	const perfil = mkdtempSync(join(tmpdir(), 'lighthouse-'));
	const chrome = await lanzarChrome(perfil);
	try {
		const { lhr } = await lighthouse(url, {
			port: chrome.port,
			output: 'json',
			logLevel: 'error',
			onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo']
		});
		const a = lhr.audits;
		resultados.push({
			rendimiento: lhr.categories.performance.score,
			accesibilidad: lhr.categories.accessibility.score,
			buenas_practicas: lhr.categories['best-practices'].score,
			seo: lhr.categories.seo.score,
			lcp: a['largest-contentful-paint'].displayValue,
			tbt: a['total-blocking-time'].displayValue,
			cls: a['cumulative-layout-shift'].displayValue
		});
	} finally {
		await chrome.kill();
		try {
			rmSync(perfil, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
		} catch (e) {
			console.warn(`No se pudo borrar el perfil temporal ${perfil}: ${e.message}`);
		}
	}
}

const ordenados = [...resultados].sort((a, b) => a.rendimiento - b.rendimiento);
const mediana = ordenados[Math.floor(ordenados.length / 2)];
const resumen = { url, corridas: resultados, mediana, minimo: MINIMO, ok: mediana.rendimiento >= MINIMO };
writeFileSync('lighthouse-resumen.json', JSON.stringify(resumen, null, 2));

const pct = (x) => Math.round(x * 100);
const texto = [
	'### Lighthouse (móvil, inicio)',
	'',
	'| Corrida | Rendimiento | Accesibilidad | Buenas prácticas | SEO | LCP | TBT | CLS |',
	'|---|---:|---:|---:|---:|---:|---:|---:|',
	...resultados.map(
		(r, i) =>
			`| ${i + 1} | ${pct(r.rendimiento)} | ${pct(r.accesibilidad)} | ${pct(r.buenas_practicas)} | ${pct(r.seo)} | ${r.lcp} | ${r.tbt} | ${r.cls} |`
	),
	'',
	`Mediana de rendimiento: **${pct(mediana.rendimiento)}** (mínimo ${pct(MINIMO)}).`
].join('\n');
console.log(texto);
if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, texto + '\n');
if (!resumen.ok) {
	console.error(`FALLA: rendimiento ${pct(mediana.rendimiento)} < ${pct(MINIMO)}`);
	process.exit(1);
}
