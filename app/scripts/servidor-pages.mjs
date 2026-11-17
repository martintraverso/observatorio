// Servidor estático que imita a GitHub Pages, para los tests e2e.
//
// - El sitio vive bajo BASE_PATH (por defecto /observatorio).
// - /ruta sirve ruta.html o ruta/index.html; si no existe, 404.html con código 404.
// - Soporta pedidos Range (los usa PMTiles), como GitHub Pages.
// - /carpeta (sin barra) redirige a /carpeta/ si solo existe carpeta/index.html, como GitHub Pages.
// - Sin dependencias: node scripts/servidor-pages.mjs [carpeta=build] [puerto=4173]
import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, normalize, resolve } from 'node:path';

const raiz = resolve(process.argv[2] ?? 'build');
const puerto = Number(process.argv[3] ?? 4173);
const base = process.env.BASE_PATH ?? '/observatorio';

const TIPOS = {
	'.html': 'text/html; charset=utf-8',
	'.js': 'text/javascript; charset=utf-8',
	'.mjs': 'text/javascript; charset=utf-8',
	'.css': 'text/css; charset=utf-8',
	'.json': 'application/json; charset=utf-8',
	'.geojson': 'application/geo+json; charset=utf-8',
	'.svg': 'image/svg+xml',
	'.woff2': 'font/woff2',
	'.woff': 'font/woff',
	'.txt': 'text/plain; charset=utf-8',
	'.pmtiles': 'application/octet-stream'
};

function archivo(ruta) {
	const relativa = normalize(decodeURIComponent(ruta)).replace(/^([/\\])+/, '');
	const p = join(raiz, relativa);
	if (!p.startsWith(raiz)) return null; // nada fuera de la carpeta
	for (const candidato of [p, `${p}.html`, join(p, 'index.html')]) {
		if (existsSync(candidato) && statSync(candidato).isFile()) return candidato;
	}
	return null;
}

function enviar(req, res, ruta, status = 200) {
	const tipo = TIPOS[extname(ruta)] ?? 'application/octet-stream';
	const tamano = statSync(ruta).size;
	const rango = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? '');
	if (status === 200 && rango) {
		let inicio = rango[1] === '' ? tamano - Number(rango[2]) : Number(rango[1]);
		let fin = rango[1] === '' || rango[2] === '' ? tamano - 1 : Math.min(Number(rango[2]), tamano - 1);
		if (Number.isNaN(inicio) || inicio < 0 || inicio > fin) {
			res.writeHead(416, { 'content-range': `bytes */${tamano}` }).end();
			return;
		}
		res.writeHead(206, {
			'content-type': tipo,
			'accept-ranges': 'bytes',
			'content-range': `bytes ${inicio}-${fin}/${tamano}`,
			'content-length': fin - inicio + 1
		});
		createReadStream(ruta, { start: inicio, end: fin }).pipe(res);
		return;
	}
	res.writeHead(status, { 'content-type': tipo, 'accept-ranges': 'bytes', 'content-length': tamano });
	createReadStream(ruta).pipe(res);
}

createServer((req, res) => {
	const url = new URL(req.url, 'http://localhost');
	if (!url.pathname.startsWith(base)) {
		res.writeHead(404).end('fuera del sitio');
		return;
	}
	const ruta = url.pathname.slice(base.length) || '/';
	const local = join(raiz, normalize(decodeURIComponent(ruta)));
	if (!ruta.endsWith('/') && !existsSync(`${local}.html`) && existsSync(join(local, 'index.html'))) {
		res.writeHead(301, { location: `${url.pathname}/${url.search}` }).end();
		return;
	}
	const encontrado = archivo(ruta);
	if (encontrado) enviar(req, res, encontrado);
	else enviar(req, res, join(raiz, '404.html'), 404);
}).listen(puerto, () => console.log(`Sirviendo ${raiz} en http://localhost:${puerto}${base}/`));
