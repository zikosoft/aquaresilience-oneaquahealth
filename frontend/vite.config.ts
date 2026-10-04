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
    hmr: process.env.VITE_HMR_CLIENT_PORT
      ? { clientPort: Number(process.env.VITE_HMR_CLIENT_PORT) }
      : undefined,
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
    // On a cold start, Vite's dependency scanner only sees STATIC imports it
    // can find by parsing `index.html`'s own import graph with esbuild.
    // Every route here loads via `component: () => import('@/views/.../XyzView.vue')`
    // (router-level code splitting), and `vite-plugin-vuetify`'s `autoImport`
    // injects each `<v-xxx>` tag's real import (e.g. `vuetify/lib/components/VBtn`)
    // via a full Vue SFC template compile — a transform esbuild's lightweight
    // scan pass does not run, so it can't see those injected imports no matter
    // how many files are listed as scan entries (confirmed: adding `src/**/*.vue`
    // as extra `entries` here had zero effect). Each Vuetify family is instead
    // only discovered the first time a route that actually uses it is visited,
    // forcing a fresh re-optimization + full page reload right then. Real
    // symptom: a cascade of "new dependencies optimized ... reloading" lines
    // as someone clicks around right after a fresh `npm install`/cache wipe,
    // and — if a navigation lands while one of those reloads is still in
    // flight — a transient "chunk-XXXX.js does not exist" error for an
    // already-stale pre-bundle hash (see P1.1: user-reported after a
    // from-scratch `docker compose build --no-cache` + volume reset).
    // Fix: explicitly `include` every Vuetify family actually used anywhere
    // in this app (verified two ways — cross-referenced against a `grep` of
    // every `<v-*` tag across `src/**/*.vue`, and against two live cold-start
    // Playwright runs through every route — both produced the same 28-item
    // list) so they're all pre-bundled in the first pass, not discovered
    // incrementally. `include` bypasses the scanner entirely for these, so
    // it works regardless of the auto-import scanning limitation above. If a
    // future view starts using a Vuetify component not in this list, the
    // same cascade will reappear for just that one component the first time
    // it's used — re-run the grep below and add it here.
    //   grep -rhoE '<v-[a-z][a-z0-9-]*' src --include='*.vue' | sort -u
    include: [
      'vuetify/lib/components/VAlert/index.mjs',
      'vuetify/lib/components/VApp/index.mjs',
      'vuetify/lib/components/VAppBar/index.mjs',
      'vuetify/lib/components/VAvatar/index.mjs',
      'vuetify/lib/components/VBtn/index.mjs',
      'vuetify/lib/components/VBtnToggle/index.mjs',
      'vuetify/lib/components/VCard/index.mjs',
      'vuetify/lib/components/VCheckbox/index.mjs',
      'vuetify/lib/components/VChip/index.mjs',
      'vuetify/lib/components/VDataTable/index.mjs',
      'vuetify/lib/components/VDialog/index.mjs',
      'vuetify/lib/components/VDivider/index.mjs',
      'vuetify/lib/components/VForm/index.mjs',
      'vuetify/lib/components/VGrid/index.mjs',
      'vuetify/lib/components/VIcon/index.mjs',
      'vuetify/lib/components/VList/index.mjs',
      'vuetify/lib/components/VMain/index.mjs',
      'vuetify/lib/components/VMenu/index.mjs',
      'vuetify/lib/components/VNavigationDrawer/index.mjs',
      'vuetify/lib/components/VProgressCircular/index.mjs',
      'vuetify/lib/components/VSelect/index.mjs',
      'vuetify/lib/components/VSlider/index.mjs',
      'vuetify/lib/components/VSwitch/index.mjs',
      'vuetify/lib/components/VTable/index.mjs',
      'vuetify/lib/components/VTabs/index.mjs',
      'vuetify/lib/components/VTextField/index.mjs',
      'vuetify/lib/components/VTooltip/index.mjs',
      'vuetify/lib/components/VWindow/index.mjs',
    ],
  },
  define: {
    // Vuetify + some deps expect this in dev.
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false',
  },
})
