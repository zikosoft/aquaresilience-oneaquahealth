import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vuetify from 'vite-plugin-vuetify'

export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
  },
  optimizeDeps: {
    // maplibre-gl ships its map-render worker as a separate chunk loaded at
    // runtime via `new Worker(new URL(...), import.meta.url)`. Vite's esbuild
    // dependency pre-bundler rewrites/rehashes the main maplibre-gl module
    // into node_modules/.vite/deps/, but does not correctly follow and
    // re-bundle that dynamically-constructed worker URL, so the browser ends
    // up requesting a "maplibre-gl-worker.mjs" file that was never written
    // there. Excluding maplibre-gl from the optimizer serves it as native
    // ESM straight from node_modules instead, where the worker's relative
    // import resolves correctly. This is the fix documented by the
    // maplibre-gl-js project itself for Vite consumers.
    exclude: ['maplibre-gl'],
  },
  define: {
    // Vuetify + some deps expect this in dev.
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false',
  },
})
