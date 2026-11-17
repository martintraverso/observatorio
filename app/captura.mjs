import { chromium } from '@playwright/test';
const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
await p.goto('http://localhost:4199/observatorio/?indicador=viviendas_total&nivel=seccion&periodo=2023&territorio=seccion/0701');
await p.waitForTimeout(5000);
await p.screenshot({ path: process.argv[2] });
await b.close();
