// Colores del mapa (SYSTEM.md §8): rampa secuencial azul de 5 pasos.

export const RAMPA = ['#eaf1f8', '#c3d7ec', '#8db4db', '#4f86c0', '#1f5a96'] as const;
export const COLOR_SIN_DATO = '#d9dde1';
export const COLOR_SELECCION = '#e07a1f';
export const ATRIBUCION_MAPA = 'Límites: INE, unidades geoestadísticas 2023';

/** n colores de la rampa, repartidos de claro a oscuro (n <= 5). */
export function coloresClases(n: number): string[] {
	if (n <= 0) return [];
	if (n === 1) return [RAMPA[2]];
	return Array.from({ length: n }, (_, i) => RAMPA[Math.round((i * (RAMPA.length - 1)) / (n - 1))]);
}
