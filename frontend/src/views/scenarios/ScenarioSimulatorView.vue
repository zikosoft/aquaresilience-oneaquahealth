<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import FactorContribution from '@/components/charts/FactorContribution.vue'
import RiskGauge from '@/components/charts/RiskGauge.vue'
import ScenarioComparison from '@/components/charts/ScenarioComparison.vue'
import ResilienceMap from '@/components/map/ResilienceMap.vue'
import { fetchCurrentRisk } from '@/services/riskApi'
import { simulateScenario } from '@/services/scenarioApi'
import { useAuthStore } from '@/stores/auth'
import type { RiskScore, ScenarioSimulateResponse } from '@/types'
import { severityColor } from '@/utils/risk'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const canRun = computed(() => authStore.can('SCENARIOS', 'EXECUTE'))

const rainfall = ref(0)
const riverLevel = ref(0)

const currentRisk = ref<RiskScore | null>(null)
const result = ref<ScenarioSimulateResponse | null>(null)
const loading = ref(false)
const errorMessage = ref<string | null>(null)
const mapView = ref<'current' | 'projected'>('current')

onMounted(async () => {
  try {
    currentRisk.value = await fetchCurrentRisk()
  } catch {
    // Non-fatal: the "Current" side simply stays empty until a simulation runs.
  }
})

async function runSimulation(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    result.value = await simulateScenario({
      rainfall_adjustment_pct: rainfall.value,
      river_level_adjustment_pct: riverLevel.value,
      language: locale.value,
      include_ai_explanation: true,
    })
    currentRisk.value = result.value.current
    mapView.value = 'projected'
  } catch {
    errorMessage.value = t('scenarios.errorPrefix')
  } finally {
    loading.value = false
  }
}

const currentGaugeValue = computed(() => (currentRisk.value ? Math.round(currentRisk.value.score) : null))
const projectedGaugeValue = computed(() => (result.value ? Math.round(result.value.projected.score) : null))

const factorItems = computed(() => {
  const source = result.value ? result.value.projected : currentRisk.value
  return source ? source.factors.map((f) => ({ factor: f.label, contribution: f.contribution })) : null
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
          <v-slider
            v-model="rainfall"
            :label="t('scenarios.controls.rainfall')"
            min="-50"
            max="100"
            step="5"
            thumb-label
            class="mt-6"
            :disabled="!canRun"
          />
          <v-slider
            v-model="riverLevel"
            :label="t('scenarios.controls.riverLevel')"
            min="-50"
            max="100"
            step="5"
            thumb-label
            :disabled="!canRun"
          />
          <v-btn
            color="primary"
            block
            :disabled="!canRun"
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
            v-if="result.projected_warning.message"
            class="text-body-2 mb-2"
          >
            {{ result.projected_warning.message }}
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
