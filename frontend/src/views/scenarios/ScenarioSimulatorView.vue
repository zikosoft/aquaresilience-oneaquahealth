<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import FactorContribution from '@/components/charts/FactorContribution.vue'
import RiskGauge from '@/components/charts/RiskGauge.vue'
import ScenarioComparison from '@/components/charts/ScenarioComparison.vue'
import ResilienceMap from '@/components/map/ResilienceMap.vue'
import { fetchCurrentRisk } from '@/services/riskApi'
import { simulateScenario } from '@/services/scenarioApi'
import { useAuthStore } from '@/stores/auth'
import { useCityStore } from '@/stores/city'
import type { RiskScore, ScenarioSimulateResponse } from '@/types'
import { factorTranslationKey, leadingFactorKey, severityColor } from '@/utils/risk'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const cityStore = useCityStore()
const canRun = computed(() => authStore.can('SCENARIOS', 'EXECUTE'))

// Session 019 — WOW #2: same city-selector honesty pattern as the Command
// Center (see CommandCenterView.vue's own cityHasLiveData/cityLabel). A
// scenario run against a city with no live connector would otherwise
// silently project Toulouse's real data under that city's label.
const cityHasLiveData = computed(() => cityStore.selectedCity?.has_live_data ?? true)
const cityLabel = computed(() => {
  const city = cityStore.selectedCity
  if (!city) return ''
  const byLocale: Record<string, string> = { en: city.label_en, fr: city.label_fr, es: city.label_es }
  return byLocale[locale.value] ?? city.label_en
})

const rainfall = ref(0)
const riverLevel = ref(0)

const currentRisk = ref<RiskScore | null>(null)
const result = ref<ScenarioSimulateResponse | null>(null)
const loading = ref(false)
const errorMessage = ref<string | null>(null)
const mapView = ref<'current' | 'projected'>('current')

// Session 019 — WOW #2: one-click scenario presets. Deliberately just a
// list of RELATIVE % adjustments (fed straight into the same
// rainfall/riverLevel sliders "Run Simulation" already uses) — no absolute
// mm thresholds, no city-specific tuning. Whichever city is selected in
// the header, a preset applies the same relative "what if" to that city's
// own current baseline, so this list never needs touching when another
// city gets a live connector later (per the user's explicit request).
interface ScenarioPreset {
  key: string
  icon: string
  rainfallPct: number
  riverPct: number
}
const SCENARIO_PRESETS: ScenarioPreset[] = [
  { key: 'lightRain', icon: 'mdi-weather-rainy', rainfallPct: 30, riverPct: 10 },
  { key: 'severeStorm', icon: 'mdi-weather-lightning-rainy', rainfallPct: 100, riverPct: 50 },
  { key: 'extremeFlood', icon: 'mdi-waves-arrow-up', rainfallPct: 200, riverPct: 120 },
]
// Derived, not stored: a preset reads as "active" only while the sliders
// still match its exact values — dragging a slider away from a preset (or
// switching city, which resets the sliders) un-highlights it automatically
// instead of tracking a separate, easily-stale "last clicked preset" flag.
function isPresetActive(preset: ScenarioPreset): boolean {
  return rainfall.value === preset.rainfallPct && riverLevel.value === preset.riverPct
}

async function loadCurrentRisk(): Promise<void> {
  try {
    currentRisk.value = await fetchCurrentRisk(cityStore.selectedCityId)
  } catch {
    // Non-fatal: the "Current" side simply stays empty until a simulation runs.
  }
}

onMounted(async () => {
  await cityStore.load()
  await loadCurrentRisk()
})

// Reload the "Current" side and drop any stale scenario result when the
// header's city selector changes — a previous city's projection must never
// linger on screen under a new city's label.
watch(
  () => cityStore.selectedCityId,
  async () => {
    result.value = null
    rainfall.value = 0
    riverLevel.value = 0
    mapView.value = 'current'
    await loadCurrentRisk()
  },
)

async function runSimulation(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    result.value = await simulateScenario({
      rainfall_adjustment_pct: rainfall.value,
      river_level_adjustment_pct: riverLevel.value,
      language: locale.value,
      include_ai_explanation: true,
      city_id: cityStore.selectedCityId,
    })
    currentRisk.value = result.value.current
    mapView.value = 'projected'
  } catch {
    errorMessage.value = t('scenarios.errorPrefix')
  } finally {
    loading.value = false
  }
}

// One click: set both sliders to the preset's values and run immediately —
// this IS the "one-click" part of WOW #2, rather than making the operator
// set the sliders then separately hit "Run Simulation".
async function applyPreset(preset: ScenarioPreset): Promise<void> {
  rainfall.value = preset.rainfallPct
  riverLevel.value = preset.riverPct
  await runSimulation()
}

const currentGaugeValue = computed(() => (currentRisk.value ? Math.round(currentRisk.value.score) : null))
const projectedGaugeValue = computed(() => (result.value ? Math.round(result.value.projected.score) : null))

const factorItems = computed(() => {
  const source = result.value ? result.value.projected : currentRisk.value
  return source
    ? source.factors.map((f) => ({ factor: t(factorTranslationKey(f.key)), contribution: f.contribution }))
    : null
})

// i18n: rebuild the projected-warning sentence client-side from the
// projected RiskScore's own structured fields (same score/severity/factors
// the gauge and chart already use) instead of the backend's pre-rendered
// English message — the non-persisting preview shares the exact same
// FACTOR_LABELS/_build_message English-only issue the real warning had.
const projectedWarningMessage = computed(() => {
  if (!result.value || !result.value.projected_warning.would_trigger) return null
  const projected = result.value.projected
  const factorKey = leadingFactorKey(projected.factors)
  return t('alerts.message', {
    score: projected.score,
    severity: t(`alerts.severity.${projected.severity.toLowerCase()}`),
    factor: factorKey ? t(factorTranslationKey(factorKey)) : '—',
  })
})

const waterLevelMax = computed(() => {
  if (!result.value) return null
  const values = [result.value.water_level_mm_current, result.value.water_level_mm_projected].filter(
    (v): v is number => v !== null,
  )
  return values.length ? Math.max(...values) * 1.2 : null
})

const precipitationMax = computed(() => {
  if (!result.value) return null
  const values = [result.value.precipitation_24h_mm_current, result.value.precipitation_24h_mm_projected].filter(
    (v): v is number => v !== null,
  )
  return values.length ? Math.max(...values) * 1.2 : null
})

const mapRiskOverride = computed<RiskScore | null>(() => {
  if (!result.value) return null
  return mapView.value === 'current' ? result.value.current : result.value.projected
})
</script>

<template>
  <div>
    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      {{ errorMessage }}
    </v-alert>

    <!-- Session 019 — WOW #2: same honesty banner as the Command Center
         (see common.city.noLiveData) — a non-demo city has no real data
         to run a scenario against, so the controls are disabled rather
         than silently projecting Toulouse's numbers under its name. -->
    <v-alert
      v-if="!cityHasLiveData"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-4"
      :title="t('common.city.noLiveData.title', { city: cityLabel })"
    >
      <div>{{ t('common.city.noLiveData.body', { city: cityLabel }) }}</div>
      <div
        v-if="cityStore.selectedCity?.planned_data_source"
        class="text-caption text-medium-emphasis mt-1"
      >
        {{ t('common.city.noLiveData.plannedSource', { source: cityStore.selectedCity.planned_data_source }) }}
      </div>
    </v-alert>

    <v-row dense>
      <v-col
        cols="12"
        md="4"
      >
        <v-card
          variant="flat"
          border
          class="pa-4"
        >
          <v-card-title class="text-subtitle-1 font-weight-bold px-0">
            {{ t('scenarios.title') }}
          </v-card-title>

          <!-- Session 019 — WOW #2: one-click presets. Same relative %
               adjustments regardless of the selected city (see
               SCENARIO_PRESETS' comment above) — clicking one sets both
               sliders and runs the simulation immediately. -->
          <div class="text-caption text-medium-emphasis mb-1">
            {{ t('scenarios.presets.title') }}
          </div>
          <div class="d-flex flex-wrap ga-2 mb-4">
            <v-btn
              v-for="preset in SCENARIO_PRESETS"
              :key="preset.key"
              size="small"
              :variant="isPresetActive(preset) ? 'flat' : 'tonal'"
              :color="isPresetActive(preset) ? 'primary' : undefined"
              :prepend-icon="preset.icon"
              :disabled="!canRun || !cityHasLiveData"
              :loading="loading && isPresetActive(preset)"
              @click="applyPreset(preset)"
            >
              {{ t(`scenarios.presets.${preset.key}`) }}
            </v-btn>
          </div>

          <v-slider
            v-model="rainfall"
            :label="t('scenarios.controls.rainfall')"
            min="-50"
            max="300"
            step="5"
            thumb-label
            class="mt-6"
            :disabled="!canRun || !cityHasLiveData"
          />
          <v-slider
            v-model="riverLevel"
            :label="t('scenarios.controls.riverLevel')"
            min="-50"
            max="300"
            step="5"
            thumb-label
            :disabled="!canRun || !cityHasLiveData"
          />
          <v-btn
            color="primary"
            block
            :disabled="!canRun || !cityHasLiveData"
            :loading="loading"
            class="mt-2"
            @click="runSimulation"
          >
            {{ t('scenarios.run') }}
          </v-btn>
          <p
            v-if="!canRun"
            class="text-caption text-medium-emphasis mt-4"
          >
            {{ t('scenarios.empty') }}
          </p>
        </v-card>

        <v-card
          v-if="result"
          variant="flat"
          border
          class="pa-4 mt-4"
        >
          <v-card-title class="text-subtitle-1 font-weight-bold px-0 d-flex align-center ga-2">
            <v-icon icon="mdi-bell-alert-outline" />
            {{ t('scenarios.warning.title') }}
          </v-card-title>
          <v-chip
            :color="result.projected_warning.would_trigger ? severityColor(result.projected_warning.severity ?? 'LOW') : 'success'"
            variant="flat"
            size="small"
            class="mb-2"
          >
            {{
              result.projected_warning.would_trigger
                ? t('scenarios.warning.wouldTrigger')
                : t('scenarios.warning.wouldNotTrigger')
            }}
          </v-chip>
          <p
            v-if="projectedWarningMessage"
            class="text-body-2 mb-2"
          >
            {{ projectedWarningMessage }}
          </p>
          <p class="text-caption text-medium-emphasis">
            {{ t('scenarios.warning.note') }}
          </p>
        </v-card>
      </v-col>

      <v-col
        cols="12"
        md="8"
      >
        <v-row dense>
          <v-col
            cols="12"
            sm="6"
          >
            <RiskGauge
              widget-id="scenario-current-gauge"
              :title="t('scenarios.current')"
              :value="currentGaugeValue"
              :label="t('scenarios.riskScore')"
              :empty-text="t('scenarios.empty')"
            />
          </v-col>
          <v-col
            cols="12"
            sm="6"
          >
            <RiskGauge
              widget-id="scenario-projected-gauge"
              :title="t('scenarios.projected')"
              :value="projectedGaugeValue"
              :label="t('scenarios.riskScore')"
              :loading="loading"
              :empty-text="t('scenarios.empty')"
            />
          </v-col>
        </v-row>

        <v-row
          dense
          class="mt-2"
        >
          <v-col cols="12">
            <div class="d-flex align-center justify-space-between mb-1">
              <span class="text-subtitle-2">{{ t('map.title') }}</span>
              <v-btn-toggle
                v-if="result"
                v-model="mapView"
                density="compact"
                variant="outlined"
                color="primary"
                mandatory
              >
                <v-btn
                  value="current"
                  size="small"
                >
                  {{ t('scenarios.map.current') }}
                </v-btn>
                <v-btn
                  value="projected"
                  size="small"
                >
                  {{ t('scenarios.map.projected') }}
                </v-btn>
              </v-btn-toggle>
            </div>
            <ResilienceMap
              widget-id="scenario-map"
              :risk-override="mapRiskOverride"
              :hero-height="320"
            />
          </v-col>
        </v-row>

        <v-row
          dense
          class="mt-2"
        >
          <v-col
            cols="12"
          >
            <FactorContribution
              widget-id="scenario-factor-contribution"
              :title="t('dashboard.factorContribution.title')"
              :items="factorItems"
              :empty-text="t('scenarios.empty')"
            />
          </v-col>
        </v-row>

        <v-row
          dense
          class="mt-2"
        >
          <v-col
            cols="12"
            md="6"
          >
            <ScenarioComparison
              widget-id="scenario-water-level"
              :title="t('scenarios.waterLevel')"
              :current-value="result?.water_level_mm_current ?? null"
              :projected-value="result?.water_level_mm_projected ?? null"
              :current-label="t('scenarios.current')"
              :projected-label="t('scenarios.projected')"
              :y-axis-max="waterLevelMax"
              :empty-text="t('scenarios.empty')"
            />
          </v-col>
          <v-col
            cols="12"
            md="6"
          >
            <ScenarioComparison
              widget-id="scenario-precipitation"
              :title="t('scenarios.precipitation')"
              :current-value="result?.precipitation_24h_mm_current ?? null"
              :projected-value="result?.precipitation_24h_mm_projected ?? null"
              :current-label="t('scenarios.current')"
              :projected-label="t('scenarios.projected')"
              :y-axis-max="precipitationMax"
              :empty-text="t('scenarios.empty')"
            />
          </v-col>
        </v-row>

        <v-row
          v-if="result"
          dense
          class="mt-2"
        >
          <v-col cols="12">
            <v-card
              variant="flat"
              border
              class="pa-4"
            >
              <v-card-title class="text-subtitle-1 font-weight-bold px-0 d-flex align-center ga-2">
                <v-icon icon="mdi-creation-outline" />
                {{ t('scenarios.ai.title') }}
              </v-card-title>
              <template v-if="result.ai_explanation">
                <p class="text-body-1 mb-3">
                  {{ result.ai_explanation.explanation }}
                </p>
                <div
                  v-if="result.ai_explanation.resilience_recommendations.length"
                  class="mb-2"
                >
                  <div class="text-subtitle-2 mb-1">
                    {{ t('scenarios.ai.recommendations') }}
                  </div>
                  <ul class="text-body-2 text-medium-emphasis pl-4">
                    <li
                      v-for="(item, i) in result.ai_explanation.resilience_recommendations"
                      :key="i"
                    >
                      {{ item }}
                    </li>
                  </ul>
                </div>
                <p class="text-caption text-medium-emphasis">
                  {{ t('scenarios.ai.confidence') }}: {{ Math.round(result.ai_explanation.confidence * 100) }}%
                </p>
              </template>
              <v-alert
                v-else-if="result.ai_explanation_error"
                type="info"
                variant="tonal"
                density="compact"
              >
                {{ t('scenarios.ai.unavailable') }} {{ result.ai_explanation_error }}
              </v-alert>
            </v-card>
          </v-col>
        </v-row>
      </v-col>
    </v-row>
  </div>
</template>
