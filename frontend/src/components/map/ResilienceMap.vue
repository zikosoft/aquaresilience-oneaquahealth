<script setup lang="ts">
import { Map as MapLibreMap, NavigationControl } from 'maplibre-gl'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import WidgetCard from '@/components/common/WidgetCard.vue'
import { useUiStore } from '@/stores/ui'

import 'maplibre-gl/dist/maplibre-gl.css'

withDefaults(
  defineProps<{
    widgetId?: string
    title?: string
    heroHeight?: string | number
  }>(),
  {
    widgetId: 'resilience-map',
    title: '',
    heroHeight: 480,
  },
)

const { t } = useI18n()
const uiStore = useUiStore()

const mapContainer = ref<HTMLDivElement | null>(null)
let map: MapLibreMap | null = null
let resizeObserver: ResizeObserver | null = null

const loading = ref(true)
const error = ref<string | null>(null)

const styleUrl = import.meta.env.VITE_MAP_STYLE_URL || 'https://demotiles.maplibre.org/style.json'
const defaultCenter: [number, number] = [
  Number(import.meta.env.VITE_MAP_DEFAULT_LON) || 1.4442,
  Number(import.meta.env.VITE_MAP_DEFAULT_LAT) || 43.6047,
]
const defaultZoom = Number(import.meta.env.VITE_MAP_DEFAULT_ZOOM) || 11

function initMap(): void {
  if (!mapContainer.value) return
  try {
    const instance = new MapLibreMap({
      container: mapContainer.value,
      style: styleUrl,
      center: defaultCenter,
      zoom: defaultZoom,
      attributionControl: { compact: true },
    })
    instance.addControl(new NavigationControl({ visualizePitch: false }), 'top-right')
    instance.on('load', () => {
      loading.value = false
    })
    instance.on('error', (e) => {
      error.value = t('map.styleUnavailable')
      loading.value = false
       
      console.error('MapLibre error', e?.error)
    })
    map = instance

    resizeObserver = new ResizeObserver(() => instance.resize())
    resizeObserver.observe(mapContainer.value)
  } catch {
    error.value = t('map.styleUnavailable')
    loading.value = false
  }
}

onMounted(() => {
  initMap()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  map?.remove()
  map = null
})

// Resize the map when it toggles in/out of widget fullscreen.
watch(
  () => uiStore.widgetFullscreenId,
  () => {
    requestAnimationFrame(() => map?.resize())
  },
)
</script>

<template>
  <WidgetCard
    :widget-id="widgetId"
    :title="title || t('map.title')"
    :min-height="heroHeight"
  >
    <!--
      The MapLibre container must stay mounted in the DOM at all times: the
      map can only be constructed once `mapContainer` resolves to a real
      element, and it only finishes loading (clearing `loading`) after that.
      Gating this div behind WidgetCard's own `loading`/`error` slot-swap
      (as most other widgets do) would create a deadlock — the container
      would never mount, so the map could never load, so `loading` would
      never clear. Instead the container renders unconditionally and the
      loading/error states are shown as an overlay on top of it.
    -->
    <div class="aq-map-shell flex-grow-1">
      <div
        ref="mapContainer"
        class="aq-map-container"
      />
      <div
        v-if="loading"
        class="aq-map-overlay"
      >
        <v-progress-circular
          indeterminate
          color="primary"
        />
      </div>
      <div
        v-else-if="error"
        class="aq-map-overlay text-error"
      >
        <v-icon
          icon="mdi-alert-circle-outline"
          size="32"
          class="mb-2"
        />
        <span class="text-body-2">{{ error }}</span>
      </div>
    </div>
  </WidgetCard>
</template>

<style scoped>
.aq-map-shell {
  position: relative;
  width: 100%;
  min-height: 260px;
  border-radius: 8px;
  overflow: hidden;
}

.aq-map-container {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.aq-map-overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-surface), 0.85);
}
</style>
