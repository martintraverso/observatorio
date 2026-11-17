import { defineConfig } from 'vitest/config';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';

// En GitHub Pages el sitio vive en /<repo> (BASE_PATH=/observatorio); en desarrollo, en la raíz.
const base = (process.env.BASE_PATH ?? '') as '' | `/${string}`;

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// Todo se prerenderiza; 404.html atiende rutas que no existen (GitHub Pages lo sirve solo).
			adapter: adapter({ fallback: '404.html', strict: true }),
			paths: { base },
			prerender: {
				// Las rutas de territorio salen de `entries` en src/routes/territorio/[nivel]/[codigo].
				entries: ['*'],
				concurrency: 8,
				handleHttpError: 'fail',
				handleMissingId: 'fail'
			}
		})
	],
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
