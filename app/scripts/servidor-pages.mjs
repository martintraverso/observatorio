// Servidor estático que imita a GitHub Pages, para los tests e2e.
//
// - El sitio vive bajo BASE_PATH (por defecto /observatorio).
// - /ruta sirve ruta.html o ruta/index.html; si no existe, 404.html con código 404.
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

function enviar(res, ruta, status = 200) {
	res.writeHead(status, { 'content-type': TIPOS[extname(ruta)] ?? 'application/octet-stream' });
	createReadStream(ruta).pipe(res);
}

createServer((req, res) => {
	const url = new URL(req.url, 'http://localhost');
	if (!url.pathname.startsWith(base)) {
		res.writeHead(404).end('fuera del sitio');
		return;
	}
	const encontrado = archivo(url.pathname.slice(base.length) || '/');
	if (encontrado) enviar(res, encontrado);
	else enviar(res, join(raiz, '404.html'), 404);
}).listen(puerto, () => console.log(`Sirviendo ${raiz} en http://localhost:${puerto}${base}/`));
