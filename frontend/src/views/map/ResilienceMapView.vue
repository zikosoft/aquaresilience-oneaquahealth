<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import ResilienceMap from '@/components/map/ResilienceMap.vue'

const { t } = useI18n()

const layerKeys = ['boundary', 'waterways', 'stations', 'riskZones', 'warnings', 'scenario'] as const
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
            {{ t('map.title') }}
          </v-card-title>
          <v-list density="compact">
            <v-list-item
              v-for="key in layerKeys"
              :key="key"
            >
              <template #prepend>
                <v-checkbox-btn
                  model-value
                  disabled
                />
              </template>
              <v-list-item-title>{{ t(`map.layers.${key}`) }}</v-list-item-title>
            </v-list-item>
          </v-list>
          <v-card-text class="text-caption text-medium-emphasis">
            {{ t('dashboard.placeholderNotice') }}
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>
