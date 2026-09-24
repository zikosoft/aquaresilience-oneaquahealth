<script setup lang="ts">
import type { StyleSpecification } from 'maplibre-gl'
import { Map as MapLibreMap, Marker, NavigationControl, Popup } from 'maplibre-gl'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import WidgetCard from '@/components/common/WidgetCard.vue'
import { fetchStations } from '@/services/environmentalApi'
import { fetchMapConfig } from '@/services/geographyApi'
import { fetchCurrentRisk } from '@/services/riskApi'
import { useCityStore } from '@/stores/city'
import { useUiStore } from '@/stores/ui'
import type { MapTileProvider, RiskScore, SourceHealthStatus, Station } from '@/types'

import 'maplibre-gl/dist/maplibre-gl.css'

const props = withDefaults(
  defineProps<{
    widgetId?: string
    title?: string
    heroHeight?: string | number
    // P4: when set, the risk ring/popup use this instead of calling
    // fetchCurrentRisk() — lets the Scenario Simulator reuse this exact map
    // component to show a "Current vs Projected" view without a second,
    // divergent map implementation (Stop Rule: don't rebuild what already
    // exists). Left undefined/null, behavior is 100% unchanged from P2.1.
    riskOverride?: RiskScore | null
  }>(),
  {
    widgetId: 'resilience-map',
    title: '',
    heroHeight: 480,
    riskOverride: null,
  },
)

const { t } = useI18n()
const uiStore = useUiStore()
const cityStore = useCityStore()

const mapContainer = ref<HTMLDivElement | null>(null)
let map: MapLibreMap | null = null
let resizeObserver: ResizeObserver | null = null

const loading = ref(true)
const error = ref<string | null>(null)

// A configured VITE_MAP_STYLE_URL (a vector style JSON, e.g. a MapTiler/
// maplibre demo style) is honored if set — a deployment-level escape hatch
// that always wins. Otherwise the default is one of a few plain inline
// raster styles — no external style.json fetch at all, just PNG tile
// requests straight to well-established free tile servers (P2.1: which one
// is now a runtime Settings > Map choice, `tile_provider`, instead of a
// single hardcoded default). This is deliberately more robust than
// pointing at demotiles.maplibre.org by default: that single demo CDN has
// a history of being unreachable behind some corporate/ISP networks and
// firewalls (this sandbox's own egress policy blocks it outright), while
// these are about as universally reachable as free tile sources get. See
// P1.1 hotfix: "map stuck on loading spinner" (user-reported on their own
// machine).
const configuredStyleUrl = (import.meta.env.VITE_MAP_STYLE_URL as string | undefined)?.trim()
const RASTER_STYLES: Record<MapTileProvider, StyleSpecification> = {
  osm: {
    version: 8,
    sources: {
      osm: {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OpenStreetMap contributors',
      },
    },
    layers: [{ id: 'osm-tiles', type: 'raster', source: 'osm' }],
  },
  // CARTO Positron/Dark Matter (basemaps.cartocdn.com) were removed here in
  // P4.1: CARTO now requires a free API key for its raster basemap tiles
  // (confirmed on docs.carto.com — "CARTO's free raster basemap tiles now
  // require an API key", a change made after D019 was written), which broke
  // the whole premise of this list and of Settings > Map's own copy ("no
  // account or API key needed"). The user confirmed on their own machine
  // that only Humanitarian OSM rendered cleanly, matching this. If CARTO is
  // wanted again later, it needs a real Settings > Map API-key field and a
  // documented free-tier limit (5M tiles/month), not a silent re-add here.
  //
  // The 2 remaining providers below are free, keyless raster tile sets
  // hosted by the French OSM chapter (openstreetmap.fr) — verified against
  // https://wiki.openstreetmap.org/wiki/Raster_tile_providers, no
  // account/API key needed, same as OSM standard above.
  cyclosm: {
    version: 8,
    sources: {
      cyclosm: {
        type: 'raster',
        tiles: ['a', 'b', 'c'].map((s) => `https://${s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png`),
        tileSize: 256,
        attribution: '© OpenStreetMap contributors — CyclOSM',
      },
    },
    layers: [{ id: 'cyclosm-tiles', type: 'raster', source: 'cyclosm' }],
  },
  humanitarian: {
    version: 8,
    sources: {
      humanitarian: {
        type: 'raster',
        tiles: ['a', 'b', 'c'].map((s) => `https://${s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png`),
        tileSize: 256,
        attribution: '© OpenStreetMap contributors — Humanitarian OSM Team',
      },
    },
    layers: [{ id: 'humanitarian-tiles', type: 'raster', source: 'humanitarian' }],
  },
}
// Env-var overrides for center/zoom are a deployment-level escape hatch too
// (preserved unchanged); otherwise the fallback below matches Toulouse's
// own seeded City defaults exactly, so a failed `/geography/map-config`
// fetch degrades to precisely today's pre-P2.1 behavior, not a broken map.
const envCenterLon = Number(import.meta.env.VITE_MAP_DEFAULT_LON) || undefined
const envCenterLat = Number(import.meta.env.VITE_MAP_DEFAULT_LAT) || undefined
const envZoom = Number(import.meta.env.VITE_MAP_DEFAULT_ZOOM) || undefined
const FALLBACK_CENTER: [number, number] = [envCenterLon ?? 1.4442, envCenterLat ?? 43.6047]
const FALLBACK_ZOOM = envZoom ?? 11

// P2.1 follow-up: Settings > Map's tile provider is the deployment-wide
// *default* — a viewer can personally switch base map via the on-map layer
// picker below, without touching Settings (no ADMINISTRATION permission
// needed for that, it's just their own view). The choice is saved per
// viewer in localStorage, same "saved and reused across sessions, no
// server round trip" model as D017's dashboard time-range selector.
const MAP_PROVIDER_STORAGE_KEY = 'aquaresilience.mapTileProvider'
const KNOWN_PROVIDERS: MapTileProvider[] = ['osm', 'cyclosm', 'humanitarian']

function loadStoredProvider(): MapTileProvider | null {
  try {
    const raw = localStorage.getItem(MAP_PROVIDER_STORAGE_KEY)
    return raw && (KNOWN_PROVIDERS as string[]).includes(raw) ? (raw as MapTileProvider) : null
  } catch {
    return null
  }
}

function saveStoredProvider(provider: MapTileProvider | null): void {
  try {
    if (provider) localStorage.setItem(MAP_PROVIDER_STORAGE_KEY, provider)
    else localStorage.removeItem(MAP_PROVIDER_STORAGE_KEY)
  } catch {
    // per-viewer convenience only — a failed save just means the choice
    // won't persist to the next session, nothing else depends on it.
  }
}

// Hidden entirely when a deployment vector style URL is configured (that
// escape hatch is a single external style, not one of these 3 raster
// options, so there is nothing meaningful to switch between).
const showLayerPicker = !configuredStyleUrl
const activeProvider = ref<MapTileProvider | null>(null)
const defaultProvider = ref<MapTileProvider>('osm')
const layerPickerOpen = ref(false)
// P4.1: Settings > Map-configurable opacity (0-100) for the risk-level
// circle layer — see the RISK LAYER section below. Fetched once at map
// init alongside the tile provider/city defaults (same "deployment
// default, takes effect on next load" model tile_provider already has).
const DEFAULT_RISK_LAYER_OPACITY_PCT = 35
const riskLayerOpacityPct = ref(DEFAULT_RISK_LAYER_OPACITY_PCT)

async function resolveMapConfig(): Promise<{ style: string | StyleSpecification; center: [number, number]; zoom: number }> {
  if (configuredStyleUrl) {
    // The vector style URL escape hatch also implies its own idea of
    // center/zoom (baked into the style, or the env vars above) — skip the
    // settings/city round trip entirely in that case.
    return { style: configuredStyleUrl, center: FALLBACK_CENTER, zoom: FALLBACK_ZOOM }
  }
  try {
    const config = await fetchMapConfig()
    defaultProvider.value = config.tile_provider
    riskLayerOpacityPct.value = config.risk_layer_opacity ?? DEFAULT_RISK_LAYER_OPACITY_PCT
    const provider = loadStoredProvider() ?? config.tile_provider
    activeProvider.value = provider
    const style = RASTER_STYLES[provider] ?? RASTER_STYLES.osm
    // Session 018: honor the header's city selector (already loaded by
    // AppHeader by the time this mounts in practice; config.cities[0]
    // remains the fallback if the store hasn't resolved yet for some
    // reason, same as before this change).
    const city = cityStore.selectedCity ?? config.cities[0]
    const center: [number, number] = [
      envCenterLon ?? city?.default_lon ?? FALLBACK_CENTER[0],
      envCenterLat ?? city?.default_lat ?? FALLBACK_CENTER[1],
    ]
    const zoom = envZoom ?? city?.default_zoom ?? FALLBACK_ZOOM
    return { style, center, zoom }
  } catch (e) {
    // Never let a Settings/geography fetch failure keep the map from
    // rendering at all — fall back to the same defaults this component
    // always used before P2.1.
    console.error('Failed to load map configuration, using defaults', e)
    const provider = loadStoredProvider() ?? 'osm'
    activeProvider.value = provider
    return { style: RASTER_STYLES[provider] ?? RASTER_STYLES.osm, center: FALLBACK_CENTER, zoom: FALLBACK_ZOOM }
  }
}

const PROVIDER_I18N_KEY: Record<MapTileProvider, string> = {
  osm: 'osm',
  cyclosm: 'cyclosm',
  humanitarian: 'humanitarian',
}

function selectProvider(provider: MapTileProvider): void {
  layerPickerOpen.value = false
  if (!map || provider === activeProvider.value) return
  activeProvider.value = provider
  saveStoredProvider(provider === defaultProvider.value ? null : provider)
  // A manual switch is also the natural recovery action from a stale error
  // overlay left over from a previous provider's tile issue — clear it here
  // rather than waiting on another 'load' event that setStyle() won't fire
  // again (see initialStyleLoaded above; 'load' is only ever emitted once).
  error.value = null
  // Markers/popups are plain DOM overlays positioned via the map's own
  // projection, not style layers — they survive setStyle() untouched, so
  // there is no need to re-fetch stations or re-add them here.
  map.setStyle(RASTER_STYLES[provider] ?? RASTER_STYLES.osm)
}

const healthColor: Record<SourceHealthStatus, string> = {
  fresh: '#1E8E5A',
  stale: '#C77700',
  degraded: '#B3261E',
}

// P2.1: map risk layer — reuses the same deterministic risk score already
// computed for the Command Center (D008/`fetchCurrentRisk`, one platform-
// wide score, not per-station). Surfaced as a colored ring around the
// river gauge marker (the station the score is actually derived from) plus
// a line in its popup, rather than a separate risk-zone shape layer —
// simplest thing that makes the already-computed number visible on the
// map, matching the backlog's own "e.g. on the hydrology station marker"
// phrasing.
const RISK_RING_COLOR: Record<string, string> = {
  LOW: 'rgba(30, 142, 90, 0.55)',
  MODERATE: 'rgba(196, 130, 12, 0.55)',
  HIGH: 'rgba(210, 105, 30, 0.6)',
  CRITICAL: 'rgba(179, 38, 30, 0.65)',
}
const RISK_TEXT_COLOR: Record<string, string> = {
  LOW: '#1E8E5A',
  MODERATE: '#C4820C',
  HIGH: '#D26918',
  CRITICAL: '#B3261E',
}

// P4.1: risk level as an actual map LAYER (a real MapLibre source/layer,
// not just a marker ring) — a soft colored halo centered on the river
// gauge station, the same single platform-wide score the ring/popup above
// already anchor there (D008: one score, not per-area, so a soft halo is
// the honest shape — not a fake multi-zone heatmap implying granularity
// the risk engine doesn't compute). Opacity is Settings > Map-configurable
// (riskLayerOpacityPct); setting it to 0 there effectively hides the layer
// without needing a separate on/off control.
const RISK_LAYER_SOURCE_ID = 'aq-risk-layer-source'
const RISK_LAYER_ID = 'aq-risk-layer'
let lastRiskForLayer: RiskScore | null = null
let lastGaugeLngLat: [number, number] | null = null

function emptyFeatureCollection(): GeoJSON.FeatureCollection {
  return { type: 'FeatureCollection', features: [] }
}

// Re-adds the source/layer if missing (they don't survive setStyle(), see
// the 'style.load' hook below) and (re)syncs their data/paint to whatever
// was last computed — safe to call any number of times, in any order,
// relative to when the risk fetch actually resolves.
function syncRiskLayer(): void {
  if (!map) return
  if (!map.getSource(RISK_LAYER_SOURCE_ID)) {
    map.addSource(RISK_LAYER_SOURCE_ID, { type: 'geojson', data: emptyFeatureCollection() })
  }
  if (!map.getLayer(RISK_LAYER_ID)) {
    map.addLayer({
      id: RISK_LAYER_ID,
      type: 'circle',
      source: RISK_LAYER_SOURCE_ID,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 36, 12, 90, 16, 220],
        'circle-color': RISK_TEXT_COLOR.LOW,
        'circle-blur': 0.8,
        'circle-opacity': riskLayerOpacityPct.value / 100,
        'circle-stroke-width': 0,
      },
    })
  }
  const source = map.getSource(RISK_LAYER_SOURCE_ID) as import('maplibre-gl').GeoJSONSource
  if (lastGaugeLngLat && lastRiskForLayer) {
    source.setData({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: lastGaugeLngLat }, properties: {} }],
    })
    map.setPaintProperty(RISK_LAYER_ID, 'circle-color', RISK_TEXT_COLOR[lastRiskForLayer.severity] ?? RISK_TEXT_COLOR.LOW)
    map.setPaintProperty(RISK_LAYER_ID, 'circle-opacity', riskLayerOpacityPct.value / 100)
  } else {
    source.setData(emptyFeatureCollection())
  }
}

// P4.1: distinct icon per station kind (D016's 2 seeded stations — one
// Hub'Eau river gauge, one Open-Meteo weather point) so the 2 markers on
// the map are visually self-explanatory instead of both being a plain dot
// distinguished only by health color — user report: "je vois ... 2 points
// je ne sais pas à quoi cela correspond". See also the always-visible
// legend on the full Map page (ResilienceMapView.vue).
const STATION_KIND_ICON: Record<string, string> = {
  river_gauge: 'mdi-waves',
  weather_point: 'mdi-weather-partly-cloudy',
}

// Defensive timeout: whatever the exact cause (a blocked/slow tile host, a
// hung connection that never actively errors, ...), the loading spinner
// must never spin forever — after this many ms with no `load`/`error`
// event, force the error state instead. See P1.1 hotfix.
const MAP_LOAD_TIMEOUT_MS = 15000
let loadTimeoutId: ReturnType<typeof setTimeout> | undefined

function clearLoadTimeout(): void {
  if (loadTimeoutId !== undefined) {
    clearTimeout(loadTimeoutId)
    loadTimeoutId = undefined
  }
}

let markers: Marker[] = []

function clearStationMarkers(): void {
  markers.forEach((m) => m.remove())
  markers = []
}

function buildPopupContent(station: Station, risk: RiskScore | null): HTMLElement {
  const container = document.createElement('div')
  container.className = 'aq-station-popup'

  const title = document.createElement('div')
  title.className = 'aq-station-popup__title'
  title.textContent = station.river_name ? `${station.name}` : station.name
  container.appendChild(title)

  const subtitle = document.createElement('div')
  subtitle.className = 'aq-station-popup__subtitle'
  subtitle.textContent = station.river_name ? `${station.river_name} · ${station.city}` : station.city
  container.appendChild(subtitle)

  const list = document.createElement('dl')
  list.className = 'aq-station-popup__readings'
  for (const reading of station.latest) {
    const dt = document.createElement('dt')
    dt.textContent = t(`map.variable.${reading.variable}`, reading.variable)
    const dd = document.createElement('dd')
    dd.textContent = `${reading.value} ${reading.unit}`
    list.appendChild(dt)
    list.appendChild(dd)
  }
  container.appendChild(list)

  // Only the river gauge is where this platform-wide score is anchored
  // visually (see the RISK_RING_COLOR comment above) — the weather station
  // popup stays as it was.
  if (risk && station.kind === 'river_gauge') {
    const riskRow = document.createElement('div')
    riskRow.className = 'aq-station-popup__risk'
    const label = document.createElement('span')
    label.textContent = `${t('map.station.risk')}: `
    const value = document.createElement('strong')
    value.textContent = `${t(`alerts.severity.${risk.severity.toLowerCase()}`)} (${Math.round(risk.score)})`
    value.style.color = RISK_TEXT_COLOR[risk.severity] ?? 'inherit'
    riskRow.appendChild(label)
    riskRow.appendChild(value)
    container.appendChild(riskRow)
  }

  if (station.latest[0]) {
    const updated = document.createElement('div')
    updated.className = 'aq-station-popup__updated'
    updated.textContent = `${t('map.station.lastUpdated')}: ${new Date(station.latest[0].observed_at).toLocaleString()}`
    container.appendChild(updated)
  }

  return container
}

async function addStationMarkers(): Promise<void> {
  if (!map) return
  clearStationMarkers()
  try {
    // Best-effort: a failed risk fetch must never keep station markers from
    // rendering at all — the map degrades to exactly its pre-P2.1 look.
    // P4: a non-null riskOverride (Scenario Simulator) skips the network
    // call entirely and uses the already-computed projected/current score
    // the caller passed in.
    const [stations, risk] = await Promise.all([
      fetchStations(),
      props.riskOverride !== null && props.riskOverride !== undefined
        ? Promise.resolve(props.riskOverride)
        : fetchCurrentRisk().catch((e) => {
            console.error('Failed to load current risk for map', e)
            return null
          }),
    ])
    lastGaugeLngLat = null
    lastRiskForLayer = null
    for (const station of stations) {
      const el = document.createElement('div')
      el.className = 'aq-station-marker'
      el.style.backgroundColor = healthColor[station.source_health] ?? healthColor.degraded
      el.setAttribute('role', 'img')
      el.setAttribute('aria-label', `${station.name} — ${t(`map.stationKind.${station.kind}`, station.kind)}`)

      const icon = document.createElement('i')
      icon.className = `mdi ${STATION_KIND_ICON[station.kind] ?? 'mdi-map-marker'} aq-station-marker__icon`
      el.appendChild(icon)

      if (station.kind === 'river_gauge' && risk) {
        const ringColor = RISK_RING_COLOR[risk.severity] ?? RISK_RING_COLOR.LOW
        el.style.boxShadow = `0 0 0 4px ${ringColor}, 0 0 0 1px rgba(0, 0, 0, 0.25)`
        el.setAttribute(
          'aria-label',
          `${station.name} — ${t(`map.stationKind.${station.kind}`, station.kind)} — ${t('map.station.risk')}: ${t(`alerts.severity.${risk.severity.toLowerCase()}`)}`,
        )
        lastGaugeLngLat = [station.lon, station.lat]
        lastRiskForLayer = risk
      }

      const popup = new Popup({ offset: 14, closeButton: true }).setDOMContent(buildPopupContent(station, risk))
      const marker = new Marker({ element: el }).setLngLat([station.lon, station.lat]).setPopup(popup).addTo(map)
      markers.push(marker)
    }
    syncRiskLayer()
  } catch (e) {

    console.error('Failed to load stations for map', e)
  }
}

// Set once the map's initial style has actually finished loading. Used to
// scope the 'error' handler below: MapLibre fires the *same* 'error' event
// both for a genuinely fatal initial style load failure and for routine,
// recoverable hiccups afterwards (a single tile 404/timeout at the edge of a
// provider's coverage, a transient network blip on one host) — e.g. the
// layer picker's own live verification hit exactly this against a tile host
// blocked only by this sandbox's own network policy, and the map was left
// permanently showing "Map style unavailable" even though every subsequent
// style switch (and its tiles) kept loading correctly underneath. Only an
// error before this first successful load is treated as fatal; anything
// after is logged but no longer takes down an otherwise-working map.
let initialStyleLoaded = false

async function initMap(): Promise<void> {
  if (!mapContainer.value) return
  const { style, center, zoom } = await resolveMapConfig()
  if (!mapContainer.value) return // component may have unmounted while awaiting
  try {
    const instance = new MapLibreMap({
      container: mapContainer.value,
      style,
      center,
      zoom,
      attributionControl: { compact: true },
    })
    instance.addControl(new NavigationControl({ visualizePitch: false }), 'top-right')
    instance.on('load', () => {
      clearLoadTimeout()
      initialStyleLoaded = true
      loading.value = false
      // Session 017 (live-verified bug): MapLibre can fire 'error' for a
      // single blocked/slow tile *before* 'load' resolves on the very first
      // paint (race, not a real failure — the style itself loads fine right
      // after). The 'error' handler below sets error.value on that first hit,
      // but nothing ever cleared it again, so a map that went on to load
      // successfully was left permanently hidden behind "Map style
      // unavailable". A successful load always supersedes an earlier error.
      error.value = null
      void addStationMarkers()
    })
    // 'style.load' fires on the initial load AND again after every
    // setStyle() (the on-map base layer picker) — unlike the DOM marker
    // overlays, the risk layer is a real style source/layer and does not
    // survive a style swap, so it must be re-added every time this fires.
    instance.on('style.load', () => {
      syncRiskLayer()
    })
    instance.on('error', (e) => {
      console.error('MapLibre error', e?.error)
      if (initialStyleLoaded) return // see initialStyleLoaded comment above
      clearLoadTimeout()
      error.value = t('map.styleUnavailable')
      loading.value = false
    })
    map = instance

    resizeObserver = new ResizeObserver(() => instance.resize())
    resizeObserver.observe(mapContainer.value)

    loadTimeoutId = setTimeout(() => {
      if (loading.value) {
        error.value = t('map.loadTimeout')
        loading.value = false
      }
    }, MAP_LOAD_TIMEOUT_MS)
  } catch {
    error.value = t('map.styleUnavailable')
    loading.value = false
  }
}

onMounted(() => {
  void initMap()
})

onBeforeUnmount(() => {
  clearLoadTimeout()
  resizeObserver?.disconnect()
  clearStationMarkers()
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

// P4: re-render markers (ring/popup only — no re-fetch of stations, no map
// re-init) whenever the Scenario Simulator flips between Current/Projected.
watch(
  () => props.riskOverride,
  () => {
    if (!loading.value) void addStationMarkers()
  },
)

// Session 018 (user request): fly to the newly selected city — a visual
// recenter only. Station markers are never re-fetched here: the backend
// has exactly one real station (Toulouse) regardless of which city is
// centered, so nothing is fabricated for the other 8 — the map honestly
// just won't show a marker nearby until that city has a connector of
// its own (see the dashboard's "no live data" banner for the rest of
// that story).
watch(
  () => cityStore.selectedCityId,
  () => {
    const city = cityStore.selectedCity
    if (!map || !city) return
    map.flyTo({
      center: [envCenterLon ?? city.default_lon, envCenterLat ?? city.default_lat],
      zoom: envZoom ?? city.default_zoom,
    })
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
      <!--
        On-map base layer picker. Settings > Map still sets the deployment
        default (shown as "(default)" below); this lets any viewer switch
        their own view without touching Settings — saved per-browser, not
        sent anywhere.
      -->
      <v-menu
        v-if="showLayerPicker && !loading"
        v-model="layerPickerOpen"
        location="top"
        :close-on-content-click="false"
      >
        <template #activator="{ props: menuProps }">
          <v-btn
            v-bind="menuProps"
            class="aq-layer-picker-btn"
            icon="mdi-layers-outline"
            size="small"
            :aria-label="t('map.baseMap.title')"
          />
        </template>
        <v-list
          density="compact"
          min-width="220"
        >
          <v-list-subheader>{{ t('map.baseMap.title') }}</v-list-subheader>
          <v-list-item
            v-for="provider in (['osm', 'cyclosm', 'humanitarian'] as const)"
            :key="provider"
            :active="activeProvider === provider"
            @click="selectProvider(provider)"
          >
            <template #prepend>
              <v-icon
                :icon="activeProvider === provider ? 'mdi-radiobox-marked' : 'mdi-radiobox-blank'"
                size="small"
              />
            </template>
            <v-list-item-title>
              {{ t(`map.baseMap.providers.${PROVIDER_I18N_KEY[provider]}`) }}
              <span
                v-if="provider === defaultProvider"
                class="aq-layer-picker-default"
              >{{ t('map.baseMap.defaultBadge') }}</span>
            </v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
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

/* Bottom-left: clear of MapLibre's own NavigationControl (top-right) and
   the map's side-panel legend, which sits outside this shell entirely. */
.aq-layer-picker-btn {
  position: absolute;
  left: 10px;
  bottom: 10px;
  z-index: 1;
  background: white !important;
  color: rgba(0, 0, 0, 0.75) !important;
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.1);
}

.aq-layer-picker-default {
  margin-left: 6px;
  font-size: 11px;
  font-weight: 400;
  opacity: 0.65;
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

<!--
  Unscoped on purpose: MapLibre's Marker/Popup append these elements
  imperatively via document.createElement, outside Vue's own render/patch
  cycle, so they never receive this component's scoped `data-v-*` attribute
  and a `scoped` rule would silently never match them.
-->
<style>
/* Session 017: MapLibre's popup chrome always has a white background
   (maplibre-gl.css hardcodes `.maplibregl-popup-content { background:
   #fff; }`, regardless of the app's own light/dark theme) — but its text
   was left to inherit the app's own (theme-dependent) color, which in
   dark mode is a near-white color cascaded down from Vuetify. Result:
   near-white text on Maplibre's always-white popup, i.e. invisible until
   you select it (user report: "je viens de les voir mais faut changer la
   couleur"). Forcing a guaranteed-dark, always-legible color on the
   popup's own content box (not just `.aq-station-popup`, so this also
   covers MapLibre's own close button, a sibling of that div) fixes it in
   both app themes, since the white background here never changes anyway. */
.maplibregl-popup-content {
  color: #1a1a1a;
}

.aq-station-marker {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid white;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.25);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.aq-station-marker__icon {
  font-size: 12px;
  color: white;
  line-height: 1;
}

.aq-station-popup {
  font-size: 13px;
  min-width: 180px;
}

.aq-station-popup__title {
  font-weight: 700;
  margin-bottom: 2px;
}

.aq-station-popup__subtitle {
  color: #666;
  margin-bottom: 8px;
}

.aq-station-popup__readings {
  display: grid;
  grid-template-columns: auto auto;
  column-gap: 12px;
  row-gap: 2px;
  margin: 0 0 8px;
}

.aq-station-popup__readings dt {
  color: #666;
}

.aq-station-popup__readings dd {
  margin: 0;
  font-weight: 600;
  text-align: right;
}

.aq-station-popup__updated {
  font-size: 11px;
  color: #888;
}
</style>
