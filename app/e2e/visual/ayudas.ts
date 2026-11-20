// M10.0 (#78): helpers del arnés de pruebas visuales (docs/ACCEPTANCE_CRITERIA_UI.md).
// Cada helper devuelve la lista de problemas encontrados (vacía si está todo bien), para que el
// test muestre en el mensaje de falla qué elemento falló y por qué.
import type { Page } from '@playwright/test';

/** Las cuatro vistas de todos los criterios [auto] de M10. */
export const VISTAS = [
	{ nombre: '1440', width: 1440, height: 900 },
	{ nombre: '1024', width: 1024, height: 768 },
	{ nombre: '768', width: 768, height: 1024 },
	{ nombre: '390', width: 390, height: 844 }
] as const;

/** Elementos con texto que no pueden desbordar ni quedar recortados (AC-V5). */
export const SELECTOR_TEXTOS = 'button, a, label, th, [role=tab], .kpi, .kpis dd';

/** Opciones de un control segmentado o lista de opciones: ninguna puede ocupar más de una línea (AC-V1). */
export const SELECTOR_SEGMENTADO = '.segmentado label, .lista-niveles label';

/** Textos internos del mantenedor que nunca se muestran (AC-V19). */
export const TEXTOS_INTERNOS = [/decisi[oó]n del mantenedor/i, /se deja asentado/i, /\bTODO\b/, /\bFIXME\b/];

/** Espera a que la página esté quieta: fuentes tipográficas cargadas y sin cambios de layout pendientes. */
export async function esperarQuieta(page: Page) {
	await page.waitForLoadState('load');
	await page.evaluate(async () => {
		await document.fonts.ready;
		await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
	});
}

/**
 * AC-V5 y AC-V1: texto que desborda su caja o queda recortado por un contenedor con
 * `overflow: hidden`, en `SELECTOR_TEXTOS`, y opciones de un segmentado en más de una línea.
 * No cuenta lo que está dentro de un contenedor con scroll (eso es desplazable, no recortado)
 * ni lo que no se ve (cerrado, oculto o solo para lectores de pantalla).
 */
export async function detectarDesbordes(page: Page): Promise<string[]> {
	await esperarQuieta(page);
	return page.evaluate(
		({ textos, segmentado }) => {
			const TOL = 1; // px de tolerancia por redondeo
			const problemas: string[] = [];
			const describir = (el: Element) => {
				const clase = typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).join('.') : '';
				const texto = (el.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, 50);
				return `${el.tagName.toLowerCase()}${clase} «${texto}»`;
			};
			const seVe = (el: Element) => {
				const r = el.getBoundingClientRect();
				if (r.width <= 1 || r.height <= 1) return false;
				if (!el.checkVisibility({ visibilityProperty: true, opacityProperty: true })) return false;
				// solo para lectores de pantalla (clip/clip-path a 1px)
				const cs = getComputedStyle(el);
				return !(cs.position === 'absolute' && (cs.clip.startsWith('rect(0') || cs.clipPath.startsWith('inset(50%')));
			};
			const cajas = (el: Element) => {
				const rs = [...el.getClientRects()].filter((r) => r.width > 0 && r.height > 0);
				return rs.length ? rs : [el.getBoundingClientRect()];
			};
			/** Rectángulos de las líneas de texto (sin contar inputs ni íconos). */
			const lineas = (el: Element) => {
				const tops: number[] = [];
				const caminante = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
				for (let n = caminante.nextNode(); n; n = caminante.nextNode()) {
					if (!n.textContent?.trim()) continue;
					const rango = document.createRange();
					rango.selectNodeContents(n);
					for (const r of rango.getClientRects()) {
						if (r.width < 1) continue;
						if (!tops.some((t) => Math.abs(t - r.top) < r.height / 2)) tops.push(r.top);
					}
				}
				return tops.length;
			};

			for (const el of document.querySelectorAll<HTMLElement>(textos)) {
				if (!(el.textContent ?? '').trim() || !seVe(el)) continue;
				const cs = getComputedStyle(el);
				if (cs.display !== 'inline' && cs.display !== 'contents') {
					if (el.scrollWidth > el.clientWidth + TOL) {
						problemas.push(`${describir(el)}: el texto desborda a lo ancho (${el.scrollWidth} > ${el.clientWidth} px)`);
						continue;
					}
					if (el.scrollHeight > el.clientHeight + TOL && cs.overflowY !== 'auto' && cs.overflowY !== 'scroll') {
						problemas.push(`${describir(el)}: el texto desborda a lo alto (${el.scrollHeight} > ${el.clientHeight} px)`);
						continue;
					}
				}
				// recortado por un contenedor que esconde lo que sobra
				const propias = cajas(el);
				for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
					const ca = getComputedStyle(a);
					if (ca.overflowX === 'auto' || ca.overflowX === 'scroll' || ca.overflowY === 'auto' || ca.overflowY === 'scroll') break;
					if (ca.overflowX !== 'hidden' && ca.overflowX !== 'clip' && ca.overflowY !== 'hidden' && ca.overflowY !== 'clip') continue;
					const ra = a.getBoundingClientRect();
					if (ra.width <= 1 || ra.height <= 1) break; // contenedor solo para lectores de pantalla
					const fuera = propias.some(
						(r) => r.left < ra.left - TOL || r.right > ra.right + TOL || r.top < ra.top - TOL || r.bottom > ra.bottom + TOL
					);
					if (fuera) {
						problemas.push(`${describir(el)}: queda recortado por ${describir(a).split(' «')[0]}`);
						break;
					}
				}
			}

			for (const el of document.querySelectorAll<HTMLElement>(segmentado)) {
				if (!seVe(el)) continue;
				const n = lineas(el);
				if (n > 1) problemas.push(`${describir(el)}: la opción ocupa ${n} líneas`);
			}
			return problemas;
		},
		{ textos: SELECTOR_TEXTOS, segmentado: SELECTOR_SEGMENTADO }
	);
}

/**
 * AC-V1: el control segmentado muestra todas sus opciones en una sola fila o en una lista
 * vertical (ninguna sola en una fila), todas de la misma altura y sin texto en más de una línea.
 * `contenedor` es el selector del grupo (p. ej. el fieldset «Nivel territorial»).
 */
export async function revisarSegmentado(page: Page, contenedor: string): Promise<string[]> {
	await esperarQuieta(page);
	const problemas: string[] = [];
	const opciones = await page.locator(contenedor).locator('label').evaluateAll((ls) =>
		ls.map((l) => {
			const r = l.getBoundingClientRect();
			const tops: number[] = [];
			const caminante = document.createTreeWalker(l, NodeFilter.SHOW_TEXT);
			for (let n = caminante.nextNode(); n; n = caminante.nextNode()) {
				if (!n.textContent?.trim()) continue;
				const rango = document.createRange();
				rango.selectNodeContents(n);
				for (const c of rango.getClientRects()) if (c.width >= 1 && !tops.some((t) => Math.abs(t - c.top) < c.height / 2)) tops.push(c.top);
			}
			return { texto: (l.textContent ?? '').trim().replace(/\s+/g, ' '), top: Math.round(r.top), alto: Math.round(r.height), lineas: tops.length };
		})
	);
	for (const o of opciones) if (o.lineas > 1) problemas.push(`«${o.texto}»: la opción ocupa ${o.lineas} líneas`);
	if (opciones.length === 0) return [`no encuentro opciones en ${contenedor}`];
	const filas = new Map<number, string[]>();
	for (const o of opciones) {
		const fila = [...filas.keys()].find((t) => Math.abs(t - o.top) <= 2) ?? o.top;
		filas.set(fila, [...(filas.get(fila) ?? []), o.texto]);
	}
	const porFila = [...filas.values()].map((f) => f.length);
	const unaFila = filas.size === 1;
	const vertical = porFila.every((n) => n === 1);
	if (!unaFila && !vertical) {
		problemas.push(`las ${opciones.length} opciones no están en una fila ni en una lista vertical: ${[...filas.values()].map((f) => f.join(' | ')).join(' / ')}`);
	}
	const altos = new Set(opciones.map((o) => o.alto));
	if (altos.size > 1) problemas.push(`las opciones tienen alturas distintas: ${opciones.map((o) => `${o.texto} ${o.alto} px`).join(', ')}`);
	return problemas;
}

/** AC-V19: la página no contiene textos internos del mantenedor (ni en el texto visible ni en el cerrado, ni en atributos). */
export async function sinTextoInterno(page: Page): Promise<string[]> {
	await page.waitForLoadState('load');
	const { texto, atributos } = await page.evaluate(() => {
		// nodos de texto separados por espacios, para que «Copiar» + «FIXME» no queden pegados
		const partes: string[] = [];
		const caminante = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
			acceptNode: (n) => (n.parentElement?.closest('script, style, template, noscript') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT)
		});
		for (let n = caminante.nextNode(); n; n = caminante.nextNode()) partes.push(n.textContent ?? '');
		const atributos = [...document.body.querySelectorAll('[title], [aria-label], [alt], [placeholder]')].flatMap((el) =>
			['title', 'aria-label', 'alt', 'placeholder'].map((a) => el.getAttribute(a) ?? '').filter(Boolean)
		);
		return { texto: partes.join(' '), atributos };
	});
	const problemas: string[] = [];
	for (const patron of TEXTOS_INTERNOS) {
		for (const fuente of [texto, ...atributos]) {
			const m = fuente.match(patron);
			if (!m) continue;
			const i = m.index ?? 0;
			problemas.push(`texto interno ${patron}: «…${fuente.slice(Math.max(0, i - 20), i + 60).replace(/\s+/g, ' ').trim()}…»`);
			break;
		}
	}
	return problemas;
}

/** En celular y tableta los controles del mapa están en una hoja que abre la barra «… Cambiar» (AC-V13): la abre si hace falta. */
export async function abrirOpciones(page: Page) {
	const barra = page.getByRole('button', { name: /Cambiar$/ });
	if (await barra.isVisible()) {
		await barra.click();
		await page.locator('#controles-mapa').waitFor({ state: 'visible' });
	}
}
