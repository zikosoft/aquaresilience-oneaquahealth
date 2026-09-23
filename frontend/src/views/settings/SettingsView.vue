<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import AIProviderSettings from '@/components/settings/AIProviderSettings.vue'
import GenericSettingCard from '@/components/settings/GenericSettingCard.vue'
import UsersAccessSettings from '@/components/settings/UsersAccessSettings.vue'
import SourceHealthBadge from '@/components/common/SourceHealthBadge.vue'
import { extractApiErrorMessage } from '@/services/api'
import { fetchSources } from '@/services/environmentalApi'
import { fetchCities } from '@/services/geographyApi'
import { useAuthStore } from '@/stores/auth'
import type { City, SourceHealth } from '@/types'

const { t, locale } = useI18n()
const route = useRoute()
const authStore = useAuthStore()

const initialTab = typeof route.query.tab === 'string' ? route.query.tab : 'general'
const tab = ref(initialTab)

const canAdminister = authStore.can('ADMINISTRATION', 'VIEW')

// Settings > Data Sources: was a static P0 placeholder that never showed the
// real sources added in P1 even though the /sources page (same data) did.
// Fixed in the P1.1 hotfix by fetching the same real data here.
const dataSources = ref<SourceHealth[]>([])
const dataSourcesLoading = ref(true)
const dataSourcesError = ref<string | null>(null)

async function loadDataSources(): Promise<void> {
  dataSourcesLoading.value = true
  dataSourcesError.value = null
  try {
    dataSources.value = await fetchSources()
  } catch (e) {
    dataSourcesError.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    dataSourcesLoading.value = false
  }
}

// Settings > Map: the tile-provider picker is a generic setting (edited
// like any other category), but the default view is a read-only display of
// the configured City's own lat/lon/zoom (D016) — deliberately not a
// second editable copy of the same numbers, see app/seed/seed_data.py.
const cities = ref<City[]>([])
const citiesLoading = ref(true)
const citiesError = ref<string | null>(null)

async function loadCities(): Promise<void> {
  citiesLoading.value = true
  citiesError.value = null
  try {
    cities.value = await fetchCities()
  } catch (e) {
    citiesError.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    citiesLoading.value = false
  }
}

onMounted(loadDataSources)
onMounted(loadCities)

// P4.1: General > city was free text even though the City reference table
// (D016) already exists and is seeded — a dropdown communicates that the
// platform is built for more than one city/country without building any
// real multi-city switching logic (D016 still applies: one seeded city).
// The stored value keeps the exact same shape it always had (the lowercase
// slug "toulouse", see app/seed/seed_data.py) so this is a UI-only change.
function localizedCityLabel(city: City): string {
  const key = `label_${locale.value}` as 'label_en' | 'label_fr' | 'label_es'
  return city[key] || city.label_en
}

function countryDisplayName(iso2: string): string {
  try {
    return new Intl.DisplayNames([locale.value], { type: 'region' }).of(iso2) ?? iso2
  } catch {
    return iso2
  }
}

const generalFields = computed(() => [
  {
    path: 'city',
    label: t('settings.general.city'),
    type: 'select' as const,
    options: cities.value.map((city) => ({
      value: city.label_en.toLowerCase(),
      label: `${localizedCityLabel(city)} (${countryDisplayName(city.country_iso2)})`,
    })),
  },
  { path: 'timezone', label: t('settings.general.timezone'), type: 'text' as const },
  { path: 'date_format', label: t('settings.general.dateFormat'), type: 'text' as const },
])
</script>

<template>
  <div>
    <h1 class="text-h5 font-weight-bold mb-4">
      {{ t('settings.title') }}
    </h1>

    <v-tabs
      v-model="tab"
      density="comfortable"
      class="mb-4"
      show-arrows
    >
      <v-tab value="general">
        {{ t('settings.tabs.general') }}
      </v-tab>
      <v-tab value="languages">
        {{ t('settings.tabs.languages') }}
      </v-tab>
      <v-tab value="data-sources">
        {{ t('settings.tabs.dataSources') }}
      </v-tab>
      <v-tab value="ai-provider">
        {{ t('settings.tabs.aiProvider') }}
      </v-tab>
      <v-tab value="risk-engine">
        {{ t('settings.tabs.riskEngine') }}
      </v-tab>
      <v-tab value="alerts">
        {{ t('settings.tabs.alerts') }}
      </v-tab>
      <v-tab value="map">
        {{ t('settings.tabs.map') }}
      </v-tab>
      <v-tab
        v-if="canAdminister"
        value="users-access"
      >
        {{ t('settings.tabs.usersAccess') }}
      </v-tab>
      <v-tab value="system">
        {{ t('settings.tabs.system') }}
      </v-tab>
    </v-tabs>

    <v-window v-model="tab">
      <v-window-item value="general">
        <v-alert
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
        >
          {{ t('settings.general.singleCityNotice') }}
        </v-alert>
        <GenericSettingCard
          category="general"
          setting-key="general"
          :title="t('settings.tabs.general')"
          :fields="generalFields"
        />
      </v-window-item>

      <v-window-item value="languages">
        <GenericSettingCard
          category="languages"
          setting-key="languages"
          :title="t('settings.tabs.languages')"
          :fields="[
            {
              path: 'default_locale',
              label: t('settings.languages.defaultLocale'),
              type: 'select',
              options: [
                { value: 'en', label: 'English' },
                { value: 'fr', label: 'Français' },
                { value: 'es', label: 'Español' },
              ],
            },
            { path: 'enabled_locales', label: t('settings.languages.enabledLocales'), type: 'chips' },
          ]"
        />
      </v-window-item>

      <v-window-item value="data-sources">
        <v-alert
          v-if="dataSourcesError"
          type="error"
          variant="tonal"
          density="compact"
          class="mb-4"
        >
          {{ dataSourcesError }}
        </v-alert>
        <v-card
          variant="flat"
          border
        >
          <v-data-table
            :headers="[
              { title: t('sources.table.name'), key: 'name' },
              { title: t('sources.table.category'), key: 'kind' },
              { title: t('sources.table.status'), key: 'health' },
              { title: t('sources.table.lastSync'), key: 'last_success_at' },
              { title: t('sources.license'), key: 'license' },
            ]"
            :items="dataSources"
            :loading="dataSourcesLoading"
            :no-data-text="t('sources.empty')"
            density="comfortable"
          >
            <template #item.health="{ item }">
              <SourceHealthBadge :health="item.health" />
            </template>
            <template #item.last_success_at="{ item }">
              <span v-if="item.last_success_at">{{ new Date(item.last_success_at).toLocaleString() }}</span>
              <span
                v-else
                class="text-medium-emphasis"
              >—</span>
            </template>
            <template #item.license="{ item }">
              <a
                v-if="item.homepage_url"
                :href="item.homepage_url"
                target="_blank"
                rel="noopener noreferrer"
                class="text-decoration-none"
              >{{ item.license }}</a>
              <span v-else>{{ item.license }}</span>
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>

      <v-window-item value="ai-provider">
        <!-- P3: the real scheduling cadence lives here
             (scheduled_analysis_interval_minutes, on AIProviderConfig) —
             a separate "Scheduler" tab used to expose a same-labeled but
             disconnected generic setting nobody read; removed rather than
             left as a trap (Session 013). -->
        <AIProviderSettings />
      </v-window-item>

      <v-window-item value="risk-engine">
        <GenericSettingCard
          category="risk_engine"
          setting-key="risk_engine"
          :title="t('settings.tabs.riskEngine')"
          :description="t('settings.riskEngine.description')"
          :fields="[
            { path: 'weights.rainfall', label: 'Rainfall weight', type: 'number', tooltip: t('settings.riskEngine.tooltips.weightsRainfall') },
            { path: 'weights.hydrology', label: 'Hydrology weight', type: 'number', tooltip: t('settings.riskEngine.tooltips.weightsHydrology') },
            { path: 'weights.environmental', label: 'Environmental weight', type: 'number', tooltip: t('settings.riskEngine.tooltips.weightsEnvironmental') },
            { path: 'weights.trend', label: 'Trend weight', type: 'number', tooltip: t('settings.riskEngine.tooltips.weightsTrend') },
            { path: 'thresholds.low', label: 'LOW → MODERATE threshold', type: 'number', tooltip: t('settings.riskEngine.tooltips.thresholdsLow') },
            { path: 'thresholds.moderate', label: 'MODERATE → HIGH threshold', type: 'number', tooltip: t('settings.riskEngine.tooltips.thresholdsModerate') },
            { path: 'thresholds.high', label: 'HIGH → CRITICAL threshold', type: 'number', tooltip: t('settings.riskEngine.tooltips.thresholdsHigh') },
          ]"
        />
      </v-window-item>

      <v-window-item value="alerts">
        <GenericSettingCard
          category="alerts"
          setting-key="alerts"
          :title="t('settings.tabs.alerts')"
          description="Early Warning lifecycle (Alerts implemented in P2)."
          :fields="[{ path: 'lifecycle', label: t('alerts.title'), type: 'chips' }]"
        />
      </v-window-item>

      <v-window-item value="map">
        <GenericSettingCard
          category="map"
          setting-key="map"
          :title="t('settings.tabs.map')"
          :description="t('settings.map.description')"
          :fields="[
            {
              path: 'tile_provider',
              label: t('settings.map.tileProvider'),
              type: 'select',
              options: [
                { value: 'osm', label: t('settings.map.providers.osm') },
                { value: 'cyclosm', label: t('settings.map.providers.cyclosm') },
                { value: 'humanitarian', label: t('settings.map.providers.humanitarian') },
              ],
            },
            {
              path: 'risk_layer_opacity',
              label: t('settings.map.riskLayerOpacity'),
              type: 'number',
              min: 0,
              max: 100,
              suffix: '%',
              tooltip: t('settings.map.riskLayerOpacityHint'),
            },
          ]"
        />

        <v-card
          variant="flat"
          border
          class="mt-4"
        >
          <v-card-item>
            <v-card-title class="text-subtitle-1 font-weight-bold">
              {{ t('settings.map.defaultView') }}
            </v-card-title>
            <v-card-subtitle>{{ t('settings.map.defaultViewHint') }}</v-card-subtitle>
          </v-card-item>
          <v-card-text>
            <v-alert
              v-if="citiesError"
              type="error"
              variant="tonal"
              density="compact"
              class="mb-3"
            >
              {{ citiesError }}
            </v-alert>
            <div
              v-if="citiesLoading"
              class="d-flex justify-center py-6"
            >
              <v-progress-circular
                indeterminate
                color="primary"
              />
            </div>
            <v-table
              v-else-if="cities.length"
              density="compact"
            >
              <thead>
                <tr>
                  <th>{{ t('settings.general.city') }}</th>
                  <th>{{ t('settings.map.longitude') }}</th>
                  <th>{{ t('settings.map.latitude') }}</th>
                  <th>{{ t('settings.map.zoom') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="city in cities"
                  :key="city.id"
                >
                  <td>{{ localizedCityLabel(city) }} ({{ countryDisplayName(city.country_iso2) }})</td>
                  <td>{{ city.default_lon }}</td>
                  <td>{{ city.default_lat }}</td>
                  <td>{{ city.default_zoom }}</td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>
      </v-window-item>

      <v-window-item
        v-if="canAdminister"
        value="users-access"
      >
        <UsersAccessSettings />
      </v-window-item>

      <v-window-item value="system">
        <GenericSettingCard
          category="system"
          setting-key="system"
          :title="t('settings.tabs.system')"
          :fields="[{ path: 'maintenance_mode', label: t('settings.system.maintenanceMode'), type: 'boolean' }]"
        />
      </v-window-item>
    </v-window>
  </div>
</template>
