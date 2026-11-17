// CSV de los valores de un territorio (AC-F5): exactamente los valores que muestra, con su origen.

import type { Ficha } from './datos.ts';

export const COLUMNAS_CSV = [
	'territorio_id',
	'nivel',
	'codigo',
	'nombre',
	'indicador',
	'periodo',
	'valor',
	'unidad',
	'es_estimado',
	'fuente',
	'archivo_origen',
	'sha256'
] as const;

function celda(v: string | number | boolean | null | undefined): string {
	const s = v === null || v === undefined ? '' : String(v);
	return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** Filas del CSV de una ficha: una por observación (valor con punto decimal, sin separador de miles). */
export function filasCsv(f: Ficha): string[][] {
	return f.observaciones.map((o) => {
		const c = f.capturas[o.captura_id];
		const fuente = c ? f.fuentes[c.fuente_id] : undefined;
		return [
			f.id,
			f.nivel,
			f.codigo,
			f.nombre,
			o.indicador,
			o.periodo,
			o.valor === null ? '' : String(o.valor),
			f.indicadores[o.indicador]?.unidad ?? '',
			o.es_estimado ? 'true' : 'false',
			fuente ? `${fuente.organismo} · ${fuente.nombre}` : '',
			c?.archivo ?? '',
			c?.sha256 ?? ''
		];
	});
}

export function csvDeFicha(f: Ficha): string {
	return [COLUMNAS_CSV as readonly string[], ...filasCsv(f)].map((fila) => fila.map(celda).join(',')).join('\r\n') + '\r\n';
}

export function nombreArchivoCsv(f: Ficha): string {
	return `observatorio_${f.nivel}_${f.codigo}.csv`;
}

/** Descarga el CSV en el navegador. */
export function descargarCsv(f: Ficha): void {
	const blob = new Blob(['﻿' + csvDeFicha(f)], { type: 'text/csv;charset=utf-8' });
	const url = URL.createObjectURL(blob);
	const a = Object.assign(document.createElement('a'), { href: url, download: nombreArchivoCsv(f) });
	document.body.append(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}
