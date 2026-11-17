import { chromium } from '@playwright/test';
const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
await p.goto('http://localhost:4199/observatorio/?indicador=pob_total&nivel=departamento&periodo=2023');
await p.waitForFunction(() => window.__mapa?.loaded() && window.__mapa.areTilesLoaded(), undefined, { timeout: 20000 });
console.log(await p.evaluate(() => {
	const m = window.__mapa, c = m.getCanvas().getBoundingClientRect();
	const out = [];
	for (const [lon, lat] of [[-57.2, -33.2], [-56.6, -33.2], [-56.9, -33.9]]) {
		const pt = m.project([lon, lat]);
		const el = document.elementFromPoint(c.x + pt.x, c.y + pt.y);
		out.push(`${Math.round(pt.x)},${Math.round(pt.y)} -> ${el?.tagName}.${el?.className} feats=${m.queryRenderedFeatures([pt.x, pt.y]).map((f) => f.properties.id).join('|')}`);
	}
	return out.join('\n');
}));
await b.close();
