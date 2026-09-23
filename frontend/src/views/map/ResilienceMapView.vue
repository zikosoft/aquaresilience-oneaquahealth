<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import ResilienceMap from '@/components/map/ResilienceMap.vue'

const { t } = useI18n()

// P4.1: this sidebar used to be a static "layers" checklist — every item
// permanently checked and disabled, none of it wired to anything real. It
// was part of what left the user unable to tell what the map's 2 markers
// meant ("je vois le point en vert toulouse 2 points je ne sais pas à quoi
// cela correspond"). Replaced with a real, always-visible legend: the 2
// station kinds actually seeded (D016 — one Hub'Eau river gauge, one
// Open-Meteo weather point, matching the icons ResilienceMap.vue now draws
// on each marker), the health-color meaning, and what the risk halo layer
// shows (opacity configurable in Settings > Map).
const stationKinds = ['river_gauge', 'weather_point'] as const
const healthLevels = ['fresh', 'stale', 'degraded'] as const

const STATION_KIND_ICON: Record<(typeof stationKinds)[number], string> = {
  river_gauge: 'mdi-waves',
  weather_point: 'mdi-weather-partly-cloudy',
}

const HEALTH_COLOR: Record<(typeof healthLevels)[number], string> = {
  fresh: '#1E8E5A',
  stale: '#C77700',
  degraded: '#B3261E',
}
</script>

<template>
  <div>
    <v-row dense>
      <v-col
        cols="12"
        md="9"
      >
        <ResilienceMap
          widget-id="map-view-main"
          :hero-height="620"
        />
      </v-col>
      <v-col
        cols="12"
        md="3"
      >
        <v-card
          variant="flat"
          border
          class="pa-2"
        >
          <v-card-title class="text-subtitle-1 font-weight-bold">
            {{ t('map.legend.title') }}
          </v-card-title>

          <v-card-text class="pt-0">
            <div class="text-overline text-medium-emphasis mb-1">
              {{ t('map.legend.markersTitle') }}
            </div>
            <div
              v-for="kind in stationKinds"
              :key="kind"
              class="d-flex align-center ga-2 mb-2"
            >
              <span class="aq-legend-marker">
                <v-icon
                  :icon="STATION_KIND_ICON[kind]"
                  size="12"
                  color="white"
                />
              </span>
              <span class="text-body-2">{{ t(`map.stationKind.${kind}`) }}</span>
            </div>

            <v-divider class="my-3" />

            <div class="text-overline text-medium-emphasis mb-1">
              {{ t('map.legend.healthTitle') }}
            </div>
            <div
              v-for="level in healthLevels"
              :key="level"
              class="d-flex align-center ga-2 mb-2"
            >
              <span
                class="aq-legend-dot"
                :style="{ backgroundColor: HEALTH_COLOR[level] }"
              />
              <span class="text-body-2">{{ t(`map.health.${level}`) }}</span>
            </div>

            <v-divider class="my-3" />

            <div class="text-overline text-medium-emphasis mb-1">
              {{ t('map.legend.riskLayerTitle') }}
            </div>
            <p class="text-body-2 text-medium-emphasis mb-0">
              {{ t('map.legend.riskLayerHint') }}
            </p>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<style scoped>
.aq-legend-marker {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background-color: rgba(0, 0, 0, 0.55);
  border: 2px solid white;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.aq-legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid white;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.25);
  flex-shrink: 0;
}
</style>
