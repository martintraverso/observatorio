import { expect, test } from '@playwright/test';
import { gzipSync } from 'node:zlib';

// AC-G6: JS inicial <= 300 KB comprimido (sin MapLibre, que el criterio excluye).
test('AC-G6: el JS inicial pesa hasta 300 KB comprimido (sin MapLibre)', async ({ page }) => {
	const scripts: { url: string; gz: number; maplibre: boolean }[] = [];
	page.on('response', async (r) => {
		if (!/\.m?js(\?|$)/.test(r.url())) return;
		const cuerpo = await r.body().catch(() => Buffer.alloc(0));
		const texto = cuerpo.toString('utf-8');
		scripts.push({
			url: r.url(),
			gz: gzipSync(cuerpo).length,
			maplibre: texto.includes('maplibregl-ctrl') || /maplibre-gl-worker/.test(r.url())
		});
	});
	await page.goto('');
	await page.waitForLoadState('networkidle');
	const propio = scripts.filter((s) => !s.maplibre).reduce((a, s) => a + s.gz, 0);
	expect(propio, scripts.map((s) => `${s.url.split('/').pop()} ${s.gz}${s.maplibre ? ' (MapLibre)' : ''}`).join('\n')).toBeLessThanOrEqual(300_000);
});
