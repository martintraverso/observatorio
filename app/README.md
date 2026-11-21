# App de Observatorio Uruguay

Sitio estático (SvelteKit 3 + `adapter-static`) que lee los archivos que arma `pipeline/web.py`. No necesita servidor: se publica en GitHub Pages en `https://<usuario>.github.io/<repo>/`.

## Correr en local

Requiere Node 24 y los datos del pipeline en `../datos/salida/web/` (`python pipeline/correr.py` desde la raíz del repo).

```bash
cd app
npm ci
npm run dev          # copia los datos a static/datos-web/ y abre el servidor de desarrollo
```

Con datos de otro lado (por ejemplo `web.zip` del último release, descomprimido): `DATOS_WEB=/ruta/a/web npm run dev`.

### Vista previa con fuentes «en preparación»

Las fuentes que se cargan pero todavía no están activas (p. ej. la ECH, hasta F2.8) quedan en el release de datos y
no en la app. Para desarrollar con ellas, armá una web aparte (no se publica; el workflow nunca usa la opción):

```sh
mkdir -p ~/.cache/otu-vista-previa
cp datos/salida/*.parquet datos/salida/observatorio.duckdb ~/.cache/otu-vista-previa/
python pipeline/web.py --salida ~/.cache/otu-vista-previa --incluir-en-preparacion
cd app && DATOS_WEB=~/.cache/otu-vista-previa/web npm run dev           # o build + test:e2e
```

Usá una salida aparte: `web.py` también reescribe `descargas/`, y con una vista previa en `datos/salida` el CSV
local incluiría la fuente en preparación (y `OBS_DATOS=completo pytest` lo marca como falla).

## Tests

```bash
npm run check                          # tipos (svelte-check)
npm run test:unit                      # vitest: formato es-UY, acceso a datos
BASE_PATH=/observatorio npm run build  # build como en GitHub Pages
npm run test:e2e                       # Playwright + axe sobre el build, servido como GitHub Pages
```

Los e2e usan `scripts/servidor-pages.mjs`, que imita a GitHub Pages: el sitio bajo `/observatorio`, `/ruta` sirve `ruta.html` y lo que no existe devuelve `404.html` con código 404. Corren en escritorio y en móvil (390 px) y verifican: carga directa de cada ruta, URL de territorios, 404 en español, números en `es-UY`, fuente y período junto a cada valor, axe sin violaciones serias o críticas, sin scroll horizontal, teclado y áreas táctiles de 44 px.

Además, `npm run test:lighthouse -- <url>` corre Lighthouse móvil 3 veces sobre el sitio servido (falla si la mediana de rendimiento es < 80). En CI y en el deploy los e2e corren también en Firefox y WebKit (Safari); en local, con `OBS_NAVEGADORES=todos` (necesita `npx playwright install firefox webkit`).

### Pruebas visuales (M10, `docs/ACCEPTANCE_CRITERIA_UI.md`)

`e2e/visual/*.visual.ts` corre en los proyectos `visual-1440`, `visual-1024`, `visual-768` y `visual-390` (Chromium, las cuatro vistas) y, en CI, también `visual-firefox-*` y `visual-safari-*` (sin capturas). Entran en `npm run test:e2e`; solas: `npx playwright test --project='visual-*'`.

- `e2e/visual/ayudas.ts`: `detectarDesbordes(page)` (AC-V5, y opciones de un segmentado en más de una línea), `revisarSegmentado(page, contenedor)` (AC-V1) y `sinTextoInterno(page)` (AC-V19). `ayudas.visual.ts` prueba que detectan cada problema sobre HTML armado a mano.
- `calidad.visual.ts`: los controles sobre cada ruta. Los problemas que el `main` todavía tiene están marcados con `pendiente(condición, historia)` (`test.fail`): el test se pone rojo cuando el problema se corrige, y la historia que lo corrige saca la marca.
- `capturas.visual.ts`: capturas de referencia de AC-V31 (Mapa, fichas, Fuentes y Datos en las cuatro vistas, solo Chromium y solo con el fixture: con los datos completos se saltean). Las referencias (`capturas.visual.ts-snapshots/*-linux.png`) son las del runner de CI, porque la letra se dibuja distinto en otras máquinas. Para actualizarlas, en un PR con la etiqueta `visual`: dejar que el CI falle, bajar el artefacto `playwright` (`gh run download <id> -n playwright`) y copiar cada `…-actual.png` como `capturas.visual.ts-snapshots/<nombre>-<proyecto>-linux.png`. Adjuntar capturas antes/después en el PR.

Playwright necesita Chromium (`npx playwright install chromium`). En Debian sin `sudo`, si faltan `libnspr4`/`libnss3`:

```bash
mkdir -p ~/.local/opt/chromium-libs && cd ~/.local/opt/chromium-libs
apt-get download libnspr4 libnss3 && for d in *.deb; do dpkg-deb -x "$d" .; done
export LD_LIBRARY_PATH=~/.local/opt/chromium-libs/usr/lib/x86_64-linux-gnu
```

## Cómo está armada

| Archivo | Qué hace |
|---|---|
| `src/lib/datos.ts` | Único lugar que sabe dónde están los datos (`datos-web/` dentro del sitio), sus tipos y cómo leerlos. |
| `src/lib/formato.ts` | Números y fechas en `es-UY` (1.300.197 · 12,5 · 17/11/2026). |
| `src/lib/tokens.css` | Colores, tipografía y medidas de `docs/SYSTEM.md` §8. |
| `src/lib/sitio.ts` | Nombre, navegación, repositorio y links de descarga. |
| `src/routes/` | Mapa (`/`), Fichas, Datos, Fuentes y `/territorio/[nivel]/[codigo]`. |
| `scripts/preparar-datos.mjs` | Copia los datos a `static/datos-web/` antes de `dev` y `build`. |

Las fuentes (Inter y Space Grotesk) van empaquetadas con la app (`@fontsource`): el sitio no hace pedidos a otros dominios.

## Decisiones

- **Prerender de todas las rutas de territorio (no SPA fallback).** Se midió: con los datos completos, prerenderizar las 5.532 páginas (5.527 territorios) lleva unos 14 s, y el sitio pesa 159 MB (la mayoría, `datos-web/`). Así cada URL `/territorio/<nivel>/<codigo>` abre directo con código 200 (AC-G3) y sirve sin JavaScript. `404.html` queda para las rutas que no existen.
- **Los datos se sirven desde el mismo sitio**, copiados de `web.zip` del último release en cada deploy, en vez de leerlos de los releases de GitHub: mismo origen, sin depender del caché de las descargas.
- **La carpeta de datos se llama `datos-web/`**, no `datos/`, para no chocar con la página `/datos`. Por lo mismo, `/fuentes` se genera como carpeta (`fuentes/index.html`).
- **El mapa arranca cuando hace falta.** MapLibre es lo más pesado del sitio: en escritorio arranca cuando el mapa se ve; en móvil, al tocarlo ("Ver el mapa interactivo"), lo que además evita que el mapa atrape el desplazamiento de la página. Sin WebGL2 el mapa muestra un aviso y el resto funciona.

## Deploy

`.github/workflows/app.yml` arma el sitio con el `web.zip` del último release de datos, corre los e2e y lo publica en GitHub Pages. Corre al mergear cambios en `app/` a `main`, cuando termina bien una corrida de datos (AC-A4) y a mano.
