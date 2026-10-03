<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import FactorContribution from '@/components/charts/FactorContribution.vue'
import KpiSparkline from '@/components/charts/KpiSparkline.vue'
import ResilienceRadar from '@/components/charts/ResilienceRadar.vue'
import RiskGauge from '@/components/charts/RiskGauge.vue'
import RiskTrajectoryChart from '@/components/charts/RiskTrajectoryChart.vue'
import SignalsTimeline from '@/components/charts/SignalsTimeline.vue'
import SourceHealthBadge from '@/components/common/SourceHealthBadge.vue'
import WidgetCard from '@/components/common/WidgetCard.vue'
import ResilienceMap from '@/components/map/ResilienceMap.vue'
import { SUPPORTED_LOCALES } from '@/i18n'
import { extractApiErrorMessage } from '@/services/api'
import { fetchEnvironmentalSummary, fetchSources } from '@/services/environmentalApi'
import { fetchIntelligenceStatus, fetchLatestBrief, triggerAnalysis } from '@/services/intelligenceApi'
import { acknowledgeWarning, fetchCurrentRisk, fetchRiskTrajectory, fetchWarnings, resolveWarning } from '@/services/riskApi'
import { useAuthStore } from '@/stores/auth'
import { useCityStore } from '@/stores/city'
import type {
  AIIntelligenceStatus,
  EarlyWarning,
  EnvironmentalSummary,
  RiskScore,
  RiskTrajectory,
  SituationBrief,
  SourceHealth,
} from '@/types'
import { factorTranslationKey, leadingFactorKey, severityColor } from '@/utils/risk'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const cityStore = useCityStore()

// Session 018 (user request): the header's city selector drives the whole
// dashboard.
const cityHasLiveData = computed(() => cityStore.selectedCity?.has_live_data ?? true)
const cityLabel = computed(() => {
  const city = cityStore.selectedCity
  if (!city) return ''
  const byLocale: Record<string, string> = { en: city.label_en, fr: city.label_fr, es: city.label_es }
  return byLocale[locale.value] ?? city.label_en
})
// Session 020 fix: Warnings have no city dimension in the backend yet (see
// app/services/city_context.get_primary_city_id's docstring — deliberately
// scoped to Toulouse only for this pass), so this must check `is_primary`,
// NOT `has_live_data` — Vienna/Ghent are also live now but are not what the
// one shared Warning row tracks. Without this distinction, selecting Vienna
// would show Toulouse's real warning under Vienna's label.
const cityTracksWarnings = computed(() => cityStore.selectedCity?.is_primary ?? true)

const loading = ref(true)
const errorMessage = ref<string | null>(null)
const summary = ref<EnvironmentalSummary | null>(null)
const sources = ref<SourceHealth[]>([])
// P2: deterministic risk score + early warnings (D008 — reused Settings >
// Risk Engine weights/thresholds; see backend `app.services.risk_engine`).
const risk = ref<RiskScore | null>(null)
// Session 018 — WOW #4: Predictive Risk Trajectory (deterministic
// extrapolation of the Risk Engine's own trend factor, see
// risk_engine.compute_risk_trajectory). Fetched alongside the current
// score; never blocks or fails the rest of the dashboard load.
const trajectory = ref<RiskTrajectory | null>(null)
const warnings = ref<EarlyWarning[]>([])
const warningActionLoading = ref(false)

// Session 022 (user request): the AI Situation Brief widget now follows the
// selected city (see services/intelligenceApi.ts + backend
// generate_situation_brief) instead of a hardcoded empty card. Loaded and
// errored independently from the rest of the dashboard (`load()` below) —
// Master Spec §19's "if AI fails: dashboard works" gate means a brief
// fetch/generation problem must never surface as the dashboard's own
// errorMessage or block its other widgets.
const brief = ref<SituationBrief | null>(null)
const briefLoading = ref(true)
const briefGenerating = ref(false)
const briefMessage = ref<string | null>(null)
const canGenerateBrief = computed(() => authStore.can('AI_INTELLIGENCE', 'EXECUTE'))
const briefLanguageLabel = computed(() => {
  if (!brief.value) return null
  return SUPPORTED_LOCALES.find((l) => l.code === brief.value?.language)?.label ?? brief.value.language
})
const briefLanguageMismatch = computed(() => !!brief.value && brief.value.language !== locale.value)

// AI provider configuration/budget is global (one shared AIProviderConfig —
// see backend's intelligence_service), unlike `brief` above which is
// per-city — used only to drive the "AI Monitoring" KPI tile below.
const aiStatus = ref<AIIntelligenceStatus | null>(null)

async function loadBrief(): Promise<void> {
  briefLoading.value = true
  try {
    const [briefResp, statusResp] = await Promise.all([
      fetchLatestBrief(cityStore.selectedCityId),
      fetchIntelligenceStatus(),
    ])
    brief.value = briefResp
    aiStatus.value = statusResp
  } catch {
    // Best-effort only — the rest of the dashboard must stay usable even if
    // this one call fails (Master Spec §19: "if AI fails, dashboard works").
    brief.value = null
    aiStatus.value = null
  } finally {
    briefLoading.value = false
  }
}

async function onGenerateBrief(): Promise<void> {
  briefGenerating.value = true
  briefMessage.value = null
  try {
    const result = await triggerAnalysis(locale.value, cityStore.selectedCityId)
    if (result.ok && result.brief) {
      brief.value = result.brief
    } else if (!result.ok) {
      briefMessage.value = result.message
    }
  } catch (e) {
    briefMessage.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    briefGenerating.value = false
  }
}

// P2.1 (D017): dashboard chart time-range selector. Saved as a per-viewer
// preference in localStorage (D017 says "saved and reused across sessions",
// not that it must be server-side) — best-effort only, never load-bearing.
const HOURS_OPTIONS = [48, 72, 96, 120] as const
const HOURS_STORAGE_KEY = 'aquaresilience.dashboardTrendHours'

function loadStoredHours(): number {
  try {
    const raw = localStorage.getItem(HOURS_STORAGE_KEY)
    const parsed = raw ? Number(raw) : NaN
    return (HOURS_OPTIONS as readonly number[]).includes(parsed) ? parsed : 48
  } catch {
    return 48
  }
}

const selectedHours = ref<number>(loadStoredHours())
const trendsLoading = ref(false)
// Echoes back the window the currently-loaded summary actually used, so
// chart titles never claim a range before the matching data has arrived.
const effectiveHours = computed(() => summary.value?.trend_window_hours ?? selectedHours.value)

// Session 022 (user report, live-caught): this chart's title used to
// hardcode "Garonne" (Toulouse's own river) regardless of the selected
// city — still showing "Garonne" while viewing Vienna, say. The real river
// name now comes from the backend (summary.water_level_river_name, read
// from the actual station behind the latest reading — see
// app/api/v1/environmental.py), falling back to a river-less generic title
// only when the selected city genuinely has none on file.
const waterLevelChartTitle = computed(() => {
  const river = summary.value?.water_level_river_name
  return river
    ? t('dashboard.waterLevel.titleWithRiver', { river, hours: effectiveHours.value })
    : t('dashboard.waterLevel.titleGeneric', { hours: effectiveHours.value })
})

// Session 017: user report — "quand on change de 48h/72h/96h/120h ils ne
// changent pas". The duration selector and its refetch were already
// correct (see onHoursChange below); the real cause was that the demo seed
// only backfilled 48h of history — until the deployment had been running
// past that point, a 72h/96h/120h request legitimately returned the exact
// same rows as 48h. Fixed at the source: BACKFILL_HOURS in
// seed_environmental.py now matches the selector's own longest option
// (120h), so all 4 buttons show genuinely distinct data out of the box.
// This notice stays as a general safety net regardless — e.g. right after
// a fresh install/reset if BACKFILL_HOURS is ever tuned down again, or in
// a real (non-demo) deployment before live ingestion has accumulated a
// full window yet — computing the actual span of history available (from
// the earliest timestamp any trend series returned) and saying so plainly
// whenever it's shorter than what was selected.
const actualDataSpanHours = computed<number | null>(() => {
  const allTimestamps = [
    ...(summary.value?.water_level_trend_timestamps ?? []),
    ...(summary.value?.precipitation_trend_timestamps ?? []),
    ...(summary.value?.temperature_trend_timestamps ?? []),
    ...(summary.value?.humidity_trend_timestamps ?? []),
  ]
  if (allTimestamps.length === 0) return null
  const earliest = allTimestamps.reduce((min, ts) => (ts < min ? ts : min), allTimestamps[0])
  return (Date.now() - new Date(earliest).getTime()) / 3_600_000
})

const limitedHistoryNotice = computed<string | null>(() => {
  const span = actualDataSpanHours.value
  // A little slack for ingestion/backfill timing jitter before flagging it.
  if (span === null || span >= effectiveHours.value - 2) return null
  return t('dashboard.timeRange.limitedHistory', { available: Math.max(1, Math.round(span)), requested: effectiveHours.value })
})

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  const cityId = cityStore.selectedCityId
  const tracksWarnings = cityTracksWarnings.value
  try {
    const [summaryData, sourcesData, riskData, trajectoryData, warningsData] = await Promise.all([
      fetchEnvironmentalSummary(selectedHours.value, cityId),
      fetchSources(),
      fetchCurrentRisk(cityId),
      fetchRiskTrajectory(cityId),
      // See cityTracksWarnings's comment above: warnings aren't city-scoped
      // server-side yet (still pinned to Toulouse), so any other city —
      // live or not — gets an honest empty list instead of Toulouse's real
      // warnings under the wrong label.
      tracksWarnings ? fetchWarnings() : Promise.resolve([]),
    ])
    summary.value = summaryData
    sources.value = sourcesData
    risk.value = riskData
    trajectory.value = trajectoryData
    warnings.value = warningsData
  } catch (e) {
    errorMessage.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    loading.value = false
  }
}

// Reload everything when the header's city selector changes.
watch(() => cityStore.selectedCityId, load)
watch(() => cityStore.selectedCityId, loadBrief)

async function onHoursChange(hours: number | undefined): Promise<void> {
  if (hours === undefined || hours === selectedHours.value) return
  selectedHours.value = hours
  try {
    localStorage.setItem(HOURS_STORAGE_KEY, String(hours))
  } catch {
    // per-viewer convenience only — a failed save just means the choice
    // won't persist to the next session, nothing else depends on it.
  }
  trendsLoading.value = true
  errorMessage.value = null
  try {
    summary.value = await fetchEnvironmentalSummary(hours, cityStore.selectedCityId)
  } catch (e) {
    errorMessage.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    trendsLoading.value = false
  }
}

async function reloadRisk(): Promise<void> {
  const cityId = cityStore.selectedCityId
  const [riskData, warningsData] = await Promise.all([
    fetchCurrentRisk(cityId),
    cityTracksWarnings.value ? fetchWarnings() : Promise.resolve([]),
  ])
  risk.value = riskData
  warnings.value = warningsData
}

async function onAcknowledgeWarning(id: string): Promise<void> {
  warningActionLoading.value = true
  errorMessage.value = null
  try {
    await acknowledgeWarning(id)
    await reloadRisk()
  } catch (e) {
    errorMessage.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    warningActionLoading.value = false
  }
}

async function onResolveWarning(id: string): Promise<void> {
  warningActionLoading.value = true
  errorMessage.value = null
  try {
    await resolveWarning(id)
    await reloadRisk()
  } catch (e) {
    errorMessage.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    warningActionLoading.value = false
  }
}

onMounted(async () => {
  // Ensure the persisted city selection (localStorage) is resolved before
  // the first fetch, so a returning viewer's chosen city applies
  // immediately instead of flashing Toulouse's data first.
  await cityStore.load()
  await Promise.all([load(), loadBrief()])
})

// The engine keeps at most one non-RESOLVED warning open at a time (see
// `evaluate_and_persist_warnings`); `warnings` is ordered newest-first.
const openWarning = computed(() => warnings.value.find((w) => w.status !== 'RESOLVED') ?? null)
const openWarningsCount = computed(() => warnings.value.filter((w) => w.status !== 'RESOLVED').length)

// --- KPI cards ---
// monitoredZones/dataSources are real, P1-backed numbers. The other four
// (resilience score, environmental risk, active warnings, AI monitoring)
// are deliberately deterministic-risk/AI concepts that P1 does not own —
// they stay as an honest "—" placeholder until P2/P3 implement them, rather
// than fabricating a number this block has no basis to compute.
// "Monitored Zones" tooltip: built from the sources already fetched for
// this same view (no extra API call) so it always stays consistent with
// the number actually shown — e.g. "2" -> "Hub'Eau Hydrométrie — Garonne à
// Toulouse, Open-Meteo — Toulouse" (user request, P1.1 hotfix).
// Session 020 fix: `sources` comes from fetchSources(), which — unlike
// summary/risk/trajectory — is deliberately global (it backs the Settings >
// Data Sources page, grouped by city, not this view). Filtering to the
// selected city here is what keeps this tooltip's list of names consistent
// with `summary.monitored_stations`, the number it's actually describing —
// without this filter it would list every city's sources under any city's
// KPI tile.
const citySources = computed(() => sources.value.filter((s) => s.city?.id === cityStore.selectedCityId))
const monitoredZonesTooltip = computed(() =>
  citySources.value.length
    ? t('dashboard.kpi.monitoredZonesTooltip', { sources: citySources.value.map((s) => s.name).join(', ') })
    : null,
)

// P2: resilience = the inverse of the deterministic risk score (a low risk
// score means a highly resilient situation); environmental risk = the score
// itself. When not all 4 factors have data yet, the caption says how many
// do, instead of silently presenting a score computed from a partial
// picture as if it were complete (P2 "insufficient data" requirement).
const factorsCaption = computed(() =>
  risk.value && risk.value.factors_available < risk.value.factors_total
    ? t('dashboard.kpi.factorsAvailable', { available: risk.value.factors_available, total: risk.value.factors_total })
    : null,
)

const kpis = computed(() => [
  {
    key: 'resilienceScore',
    icon: 'mdi-shield-check-outline',
    value: risk.value ? Math.round(100 - risk.value.score) : null,
    caption: factorsCaption.value,
    tooltip: null,
  },
  {
    key: 'environmentalRisk',
    icon: 'mdi-waves',
    value: risk.value ? Math.round(risk.value.score) : null,
    caption: risk.value ? t(`alerts.severity.${risk.value.severity.toLowerCase()}`) : null,
    tooltip: null,
  },
  {
    key: 'activeWarnings',
    icon: 'mdi-alert-outline',
    value: loading.value ? null : openWarningsCount.value,
    caption: null,
    tooltip: null,
  },
  {
    key: 'monitoredZones',
    icon: 'mdi-map-marker-radius-outline',
    value: summary.value?.monitored_stations ?? null,
    caption: null,
    tooltip: monitoredZonesTooltip.value,
  },
  {
    key: 'dataSources',
    icon: 'mdi-database-outline',
    value: summary.value ? `${summary.value.fresh_sources}/${summary.value.active_sources}` : null,
    caption: null,
    tooltip: null,
  },
  {
    key: 'aiMonitoring',
    icon: 'mdi-creation-outline',
    // Session 022 (user report): this tile used to be a permanent "—
    // Available from P3" stub, never wired up once P3 actually shipped.
    // `aiStatus` (is_configured) is global/shared across every city — see
    // its own comment above — but `brief` is this city's own latest
    // analysis, so "last analysis" genuinely reflects the selected city,
    // not whichever city happened to be analyzed most recently overall.
    value: briefLoading.value ? null : t(aiStatus.value?.is_configured ? 'intelligence.status.active' : 'intelligence.status.disabled'),
    caption: !briefLoading.value && aiStatus.value?.is_configured && brief.value
      ? new Date(brief.value.generated_at).toLocaleString()
      : null,
    tooltip: null,
  },
])

// --- Big timeline: water level (primary axis) + precipitation (secondary axis) ---
const timelineTimestamps = computed(() =>
  (summary.value?.water_level_trend_timestamps ?? []).map((ts) =>
    new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  ),
)
const timelineSeries = computed(() => {
  if (!summary.value) return []
  return [
    {
      name: waterLevelChartTitle.value,
      values: summary.value.water_level_trend,
      color: '#0B5FA5',
    },
    {
      name: t('dashboard.precipitation.title', { hours: effectiveHours.value }),
      values: summary.value.precipitation_trend,
      color: '#4FA3D1',
      yAxisIndex: 1 as const,
    },
  ]
})

// --- KPI sparklines ---
// Temperature/humidity are already ingested via the existing Open-Meteo
// connector — no new source, just exposing trends already in the data
// (P1.1 hotfix, user request to fill the row from 2 to 4 tiles).
const waterLevelSparkValues = computed(() => summary.value?.water_level_trend ?? null)
const precipitationSparkValues = computed(() => summary.value?.precipitation_trend ?? null)
const temperatureSparkValues = computed(() => summary.value?.temperature_trend ?? null)
const humiditySparkValues = computed(() => summary.value?.humidity_trend ?? null)
// P2.1: 4 more free Open-Meteo hourly variables, same trend pattern,
// reaching the requested 8-tile Command Center KPI row.
const windSpeedSparkValues = computed(() => summary.value?.wind_speed_trend ?? null)
const windDirectionSparkValues = computed(() => summary.value?.wind_direction_trend ?? null)
const surfacePressureSparkValues = computed(() => summary.value?.surface_pressure_trend ?? null)
const uvIndexSparkValues = computed(() => summary.value?.uv_index_trend ?? null)

// P4.1: compact HH:mm labels for each KPI sparkline's x-axis, built from
// the same *_trend_timestamps arrays the API already returns alongside
// each *_trend series (mirrors the big timeline's timelineTimestamps
// formatting above) — this is what makes a duration change (24h/48h/72h)
// visibly move the axis, not just the underlying values.
function formatSparkLabels(timestamps: string[] | null | undefined): string[] | null {
  if (!timestamps || timestamps.length === 0) return null
  return timestamps.map((ts) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
}
const waterLevelSparkLabels = computed(() => formatSparkLabels(summary.value?.water_level_trend_timestamps))
const precipitationSparkLabels = computed(() => formatSparkLabels(summary.value?.precipitation_trend_timestamps))
const temperatureSparkLabels = computed(() => formatSparkLabels(summary.value?.temperature_trend_timestamps))
const humiditySparkLabels = computed(() => formatSparkLabels(summary.value?.humidity_trend_timestamps))
const windSpeedSparkLabels = computed(() => formatSparkLabels(summary.value?.wind_speed_trend_timestamps))
const windDirectionSparkLabels = computed(() => formatSparkLabels(summary.value?.wind_direction_trend_timestamps))
const surfacePressureSparkLabels = computed(() => formatSparkLabels(summary.value?.surface_pressure_trend_timestamps))
const uvIndexSparkLabels = computed(() => formatSparkLabels(summary.value?.uv_index_trend_timestamps))

// --- P2: risk gauges + factor contribution ---
const resilienceGaugeValue = computed(() => (risk.value ? Math.round(100 - risk.value.score) : null))
const environmentalRiskGaugeValue = computed(() => (risk.value ? Math.round(risk.value.score) : null))
const factorContributionItems = computed(() =>
  risk.value
    ? risk.value.factors.map((f) => ({ factor: t(factorTranslationKey(f.key)), contribution: f.contribution }))
    : null,
)

// Session 019 — WOW #3: Resilience Radar. Built from the exact same
// risk.value.factors this same view already fetches per-city (see the
// `load()`/`watch(cityStore.selectedCityId, load)` pair above) — no
// separate fetch, no city-specific code, so it stays correct for whichever
// city is selected without ever needing to be touched again (per the
// user's explicit request). See ResilienceRadar.vue's own docstring for
// why this uses normalized_value rather than contribution.
const resilienceRadarItems = computed(() =>
  risk.value
    ? risk.value.factors.map((f) => ({
        factor: t(factorTranslationKey(f.key)),
        value: f.normalized_value !== null ? Math.round(f.normalized_value * 100) : 0,
        available: f.available,
      }))
    : null,
)

// i18n: rebuild the warning sentence client-side from structured fields
// (score/severity/leading factor) instead of displaying the backend's
// pre-rendered English message — see utils/risk.ts:leadingFactorKey.
const openWarningMessage = computed(() => {
  if (!openWarning.value) return null
  const factorKey = leadingFactorKey(openWarning.value.factors)
  return t('alerts.message', {
    score: openWarning.value.risk_score,
    severity: t(`alerts.severity.${openWarning.value.severity.toLowerCase()}`),
    factor: factorKey ? t(factorTranslationKey(factorKey)) : '—',
  })
})

// Session 021 fix (user report): "no active warnings" used to read the same
// whether Warnings genuinely had nothing to report for this city, or the
// city simply isn't one Warnings track at all yet (Vienna/Ghent — see
// cityTracksWarnings above). Distinguishing the two here so the panel never
// silently implies "all clear" for a city Warnings can't actually see.
const currentWarningEmptyText = computed(() =>
  cityTracksWarnings.value ? t('dashboard.currentWarning.none') : t('dashboard.currentWarning.primaryCityOnly', { city: cityLabel.value })
)
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

    <!-- Session 018 (user request): the header's city selector lets an
         operator preview any of the 9 OneAquaHealth consortium cities, but
         only Toulouse has a live connector — this banner replaces silently
         showing Toulouse's numbers under another city's name. -->
    <v-alert
      v-if="!loading && !cityHasLiveData"
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

    <v-row
      dense
      class="mb-2"
    >
      <v-col
        v-for="kpi in kpis"
        :key="kpi.key"
        cols="6"
        sm="4"
        md="2"
      >
        <v-card
          variant="flat"
          border
          class="pa-3 h-100"
        >
          <div class="d-flex align-center justify-space-between mb-1">
            <v-icon
              :icon="kpi.icon"
              color="primary"
              size="20"
            />
            <v-tooltip
              v-if="kpi.tooltip"
              :text="kpi.tooltip"
              location="top"
            >
              <template #activator="{ props: tooltipProps }">
                <v-icon
                  v-bind="tooltipProps"
                  icon="mdi-information-outline"
                  size="16"
                  color="medium-emphasis"
                />
              </template>
            </v-tooltip>
          </div>
          <div class="text-caption text-medium-emphasis aq-truncate">
            {{ t(`dashboard.kpi.${kpi.key}`) }}
          </div>
          <div class="text-h6 font-weight-bold">
            {{ kpi.value ?? '—' }}
          </div>
          <div
            v-if="kpi.caption"
            class="text-caption text-medium-emphasis"
          >
            {{ kpi.caption }}
          </div>
        </v-card>
      </v-col>
    </v-row>

    <div class="d-flex align-center justify-space-between mb-2 flex-wrap ga-2">
      <div class="text-subtitle-2 text-medium-emphasis">
        {{ t('dashboard.timeRange.label') }}
      </div>
      <v-btn-toggle
        :model-value="selectedHours"
        mandatory
        density="compact"
        variant="outlined"
        divided
        color="primary"
        :disabled="trendsLoading"
        @update:model-value="onHoursChange"
      >
        <v-btn
          v-for="opt in HOURS_OPTIONS"
          :key="opt"
          :value="opt"
          size="small"
        >
          {{ t('dashboard.timeRange.hoursShort', { hours: opt }) }}
        </v-btn>
      </v-btn-toggle>
    </div>

    <v-alert
      v-if="limitedHistoryNotice"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-2"
    >
      {{ limitedHistoryNotice }}
    </v-alert>

    <v-row
      dense
      class="mb-2"
    >
      <v-col
        cols="6"
        md="3"
      >
        <KpiSparkline
          widget-id="kpi-water-level"
          :title="waterLevelChartTitle"
          :values="waterLevelSparkValues"
          :labels="waterLevelSparkLabels"
          :loading="loading || trendsLoading"
          color="#0B5FA5"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="6"
        md="3"
      >
        <KpiSparkline
          widget-id="kpi-precipitation"
          :title="t('dashboard.precipitation.title', { hours: effectiveHours })"
          :values="precipitationSparkValues"
          :labels="precipitationSparkLabels"
          :loading="loading || trendsLoading"
          color="#4FA3D1"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="6"
        md="3"
      >
        <KpiSparkline
          widget-id="kpi-temperature"
          :title="t('dashboard.temperature.title', { hours: effectiveHours })"
          :values="temperatureSparkValues"
          :labels="temperatureSparkLabels"
          :loading="loading || trendsLoading"
          color="#D18E2C"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="6"
        md="3"
      >
        <KpiSparkline
          widget-id="kpi-humidity"
          :title="t('dashboard.humidity.title', { hours: effectiveHours })"
          :values="humiditySparkValues"
          :labels="humiditySparkLabels"
          :loading="loading || trendsLoading"
          color="#3E8E8E"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="6"
        md="3"
      >
        <KpiSparkline
          widget-id="kpi-wind-speed"
          :title="t('dashboard.windSpeed.title', { hours: effectiveHours })"
          :values="windSpeedSparkValues"
          :labels="windSpeedSparkLabels"
          :loading="loading || trendsLoading"
          color="#5B8C5A"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="6"
        md="3"
      >
        <KpiSparkline
          widget-id="kpi-wind-direction"
          :title="t('dashboard.windDirection.title', { hours: effectiveHours })"
          :values="windDirectionSparkValues"
          :labels="windDirectionSparkLabels"
          :loading="loading || trendsLoading"
          color="#B5566B"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="6"
        md="3"
      >
        <KpiSparkline
          widget-id="kpi-surface-pressure"
          :title="t('dashboard.surfacePressure.title', { hours: effectiveHours })"
          :values="surfacePressureSparkValues"
          :labels="surfacePressureSparkLabels"
          :loading="loading || trendsLoading"
          color="#7B5EA7"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="6"
        md="3"
      >
        <KpiSparkline
          widget-id="kpi-uv-index"
          :title="t('dashboard.uvIndex.title', { hours: effectiveHours })"
          :values="uvIndexSparkValues"
          :labels="uvIndexSparkLabels"
          :loading="loading || trendsLoading"
          color="#C74B50"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
    </v-row>

    <v-row
      dense
      class="mb-2"
    >
      <v-col
        cols="12"
        sm="6"
      >
        <RiskGauge
          widget-id="resilience-score-gauge"
          :title="t('dashboard.kpi.resilienceScore')"
          :value="resilienceGaugeValue"
          :label="t('dashboard.kpi.resilienceScore')"
          :loading="loading"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="12"
        sm="6"
      >
        <RiskGauge
          widget-id="environmental-risk-gauge"
          :title="t('dashboard.kpi.environmentalRisk')"
          :value="environmentalRiskGaugeValue"
          :label="t('dashboard.kpi.environmentalRisk')"
          :loading="loading"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
    </v-row>

    <v-row
      dense
      class="mb-2"
    >
      <v-col cols="12">
        <RiskTrajectoryChart
          widget-id="risk-trajectory"
          :title="t('dashboard.trajectory.title')"
          :trajectory="trajectory"
          :loading="loading"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
    </v-row>

    <v-row dense>
      <v-col
        cols="12"
        lg="8"
      >
        <ResilienceMap
          widget-id="dashboard-map"
          :hero-height="440"
        />
      </v-col>
      <v-col
        cols="12"
        lg="4"
      >
        <WidgetCard
          widget-id="situation-brief"
          :title="t('dashboard.situationBrief.title')"
          :loading="briefLoading"
          :min-height="440"
        >
          <template v-if="!brief">
            <div class="flex-grow-1 d-flex flex-column align-center justify-center text-medium-emphasis pa-4">
              <v-icon
                icon="mdi-database-off-outline"
                size="32"
                class="mb-2"
              />
              <span class="text-body-2 text-center mb-3">
                {{ t('dashboard.situationBrief.emptyForCity', { city: cityLabel }) }}
              </span>
              <v-btn
                v-if="canGenerateBrief"
                size="small"
                variant="tonal"
                color="primary"
                :loading="briefGenerating"
                prepend-icon="mdi-creation-outline"
                @click="onGenerateBrief"
              >
                {{ t('dashboard.situationBrief.generateNow') }}
              </v-btn>
              <router-link
                v-else
                :to="{ name: 'intelligence' }"
                class="text-caption mt-1"
              >
                {{ t('dashboard.situationBrief.viewFull') }}
              </router-link>
              <span
                v-if="briefMessage"
                class="text-caption text-medium-emphasis mt-2"
              >
                {{ briefMessage }}
              </span>
            </div>
          </template>
          <template v-else-if="brief">
            <div class="d-flex align-center ga-2 flex-wrap mb-2">
              <v-chip
                :color="severityColor(brief.risk_severity_snapshot)"
                variant="flat"
                size="small"
              >
                {{ t(`alerts.severity.${brief.situation}`) }}
              </v-chip>
              <span class="text-caption text-medium-emphasis">
                {{ t('intelligence.brief.confidence') }}: {{ Math.round(brief.confidence * 100) }}%
              </span>
              <v-chip
                v-if="briefLanguageMismatch"
                size="small"
                variant="outlined"
                color="medium-emphasis"
              >
                {{ t('intelligence.brief.generatedInLanguage', { language: briefLanguageLabel }) }}
              </v-chip>
              <v-spacer />
              <v-btn
                v-if="canGenerateBrief"
                size="small"
                variant="text"
                :loading="briefGenerating"
                icon="mdi-refresh"
                @click="onGenerateBrief"
              />
            </div>

            <p class="text-body-2 mb-3">
              {{ brief.summary }}
            </p>

            <div
              v-if="brief.recommendations.length"
              class="mb-2"
            >
              <div class="text-caption font-weight-bold mb-1">
                {{ t('intelligence.brief.recommendations') }}
              </div>
              <ul class="text-caption text-medium-emphasis pl-4">
                <li
                  v-for="(item, i) in brief.recommendations.slice(0, 3)"
                  :key="i"
                >
                  {{ item }}
                </li>
              </ul>
            </div>

            <span
              v-if="briefMessage"
              class="text-caption text-medium-emphasis"
            >
              {{ briefMessage }}
            </span>

            <v-spacer />
            <v-divider class="my-2" />
            <div class="text-caption text-medium-emphasis d-flex align-center justify-space-between">
              <router-link :to="{ name: 'intelligence' }">
                {{ t('dashboard.situationBrief.viewFull') }}
              </router-link>
              <span>{{ new Date(brief.generated_at).toLocaleString() }}</span>
            </div>
          </template>
        </WidgetCard>
      </v-col>
    </v-row>

    <v-row
      dense
      class="mt-2"
    >
      <v-col
        cols="12"
        md="8"
      >
        <SignalsTimeline
          widget-id="signals-timeline"
          :title="t('dashboard.timeline.title')"
          :timestamps="timelineTimestamps"
          :series="timelineSeries"
          :loading="loading || trendsLoading"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="12"
        md="4"
      >
        <WidgetCard
          widget-id="current-warning"
          :title="t('dashboard.currentWarning.title')"
          :loading="loading"
          :empty="!loading && !openWarning"
          :empty-text="currentWarningEmptyText"
          :min-height="340"
        >
          <template v-if="openWarning">
            <div class="d-flex align-center ga-2 mb-2 flex-wrap">
              <v-chip
                :color="severityColor(openWarning.severity)"
                size="small"
                variant="flat"
              >
                {{ t(`alerts.severity.${openWarning.severity.toLowerCase()}`) }}
              </v-chip>
              <v-chip
                size="small"
                variant="outlined"
              >
                {{ t(`alerts.lifecycle.${openWarning.status.toLowerCase()}`) }}
              </v-chip>
            </div>
            <p class="text-body-2 mb-2">
              {{ openWarningMessage }}
            </p>
            <p class="text-caption text-medium-emphasis mb-4">
              {{ t('dashboard.currentWarning.triggeredAt', { time: new Date(openWarning.triggered_at).toLocaleString() }) }}
            </p>
            <div class="d-flex ga-2 flex-wrap">
              <v-btn
                v-if="openWarning.status === 'ACTIVE' && authStore.can('ALERTS', 'EDIT')"
                size="small"
                variant="tonal"
                :loading="warningActionLoading"
                @click="onAcknowledgeWarning(openWarning.id)"
              >
                {{ t('alerts.actions.acknowledge') }}
              </v-btn>
              <v-btn
                v-if="authStore.can('ALERTS', 'EXECUTE')"
                size="small"
                variant="tonal"
                color="primary"
                :loading="warningActionLoading"
                @click="onResolveWarning(openWarning.id)"
              >
                {{ t('alerts.actions.resolve') }}
              </v-btn>
            </div>
          </template>
        </WidgetCard>
      </v-col>
    </v-row>

    <v-row
      dense
      class="mt-2"
    >
      <v-col
        cols="12"
        md="4"
      >
        <FactorContribution
          widget-id="factor-contribution"
          :title="t('dashboard.factorContribution.title')"
          :items="factorContributionItems"
          :loading="loading"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="12"
        md="4"
      >
        <ResilienceRadar
          widget-id="resilience-radar"
          :title="t('dashboard.resilienceRadar.title')"
          :items="resilienceRadarItems"
          :loading="loading"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="12"
        md="4"
      >
        <WidgetCard
          widget-id="source-health"
          :title="t('dashboard.sourceHealth.title')"
          :loading="loading"
          :empty="!loading && citySources.length === 0"
          :empty-text="t('sources.empty')"
          :min-height="300"
        >
          <v-list density="compact">
            <v-list-item
              v-for="source in citySources"
              :key="source.id"
            >
              <template #append>
                <SourceHealthBadge :health="source.health" />
              </template>
              <v-list-item-title>{{ source.name }}</v-list-item-title>
              <v-list-item-subtitle v-if="source.last_success_at">
                {{ new Date(source.last_success_at).toLocaleString() }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </WidgetCard>
      </v-col>
    </v-row>
  </div>
</template>
