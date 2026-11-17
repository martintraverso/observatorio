// Copia los archivos para la app (salida de pipeline/web.py) a static/datos-web/.
//
// Origen: $DATOS_WEB, o ../datos/salida/web (la salida local del pipeline).
// En el deploy, DATOS_WEB apunta a web.zip descomprimido del último release de datos.
import { cpSync, existsSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';

const origen = resolve(process.env.DATOS_WEB ?? '../datos/salida/web');
const destino = resolve('static/datos-web');

if (!existsSync(resolve(origen, 'manifest.json'))) {
	console.error(
		`No encuentro ${origen}/manifest.json.\n` +
			'Generar los datos (python pipeline/correr.py) o definir DATOS_WEB con la carpeta de web.zip.'
	);
	process.exit(1);
}

rmSync(destino, { recursive: true, force: true });
cpSync(origen, destino, { recursive: true });
console.log(`Datos copiados: ${origen} -> ${destino}`);
