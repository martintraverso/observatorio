import { chromium, devices } from '@playwright/test';
const b = await chromium.launch();
const p = await (await b.newContext({ ...devices['Pixel 7'], viewport: { width: 390, height: 844 } })).newPage();
await p.goto('http://localhost:4199/observatorio/territorio/departamento/07');
await p.waitForTimeout(1000);
console.log(JSON.stringify(await p.evaluate(() => [...document.querySelectorAll('.tabla-scroll, .indice, .indice ul, section, main, header.cabecera, .identidad, .kpis, .acciones')]
	.map((e) => `${e.tagName}.${[...e.classList].filter((c) => !c.startsWith('svelte')).join('.')}#${e.id} w=${Math.round(e.getBoundingClientRect().width)} right=${Math.round(e.getBoundingClientRect().right)}`)), null, 1));
await b.close();
