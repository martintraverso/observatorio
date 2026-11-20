// MapLibre (lo más pesado de la app) y el protocolo pmtiles:// se cargan una sola vez por página y recién
// cuando hacen falta: el mapa (M6) y el localizador de cerca de las fichas (AC-V26) comparten esta carga.
type MapLibre = typeof import('maplibre-gl');

let carga: Promise<MapLibre> | null = null;

export function cargarMapLibre(): Promise<MapLibre> {
	carga ??= Promise.all([
		import('maplibre-gl'),
		import('pmtiles'),
		// MapLibre 6 corre en un worker de módulo aparte; Vite lo copia y da su URL.
		import('maplibre-gl/dist/maplibre-gl-worker.mjs?url')
	]).then(([maplibregl, { Protocol }, { default: urlWorker }]) => {
		maplibregl.setWorkerUrl(urlWorker);
		maplibregl.addProtocol('pmtiles', new Protocol().tile);
		return maplibregl;
	});
	return carga;
}
