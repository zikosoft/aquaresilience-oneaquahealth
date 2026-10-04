<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchIntelligenceStatus, fetchLatestBrief, triggerAnalysis } from '@/services/intelligenceApi'
import { SUPPORTED_LOCALES } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { useCityStore } from '@/stores/city'
import type { AIIntelligenceStatus, SituationBrief } from '@/types'
import { severityColor } from '@/utils/risk'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const cityStore = useCityStore()
const canExecute = computed(() => authStore.can('AI_INTELLIGENCE', 'EXECUTE'))

const cityLabel = computed(() => {
  const city = cityStore.selectedCity
  if (!city) return ''
  const byLocale: Record<string, string> = { en: city.label_en, fr: city.label_fr, es: city.label_es }
  return byLocale[locale.value] ?? city.label_en
})

// A given city's current brief remembers whichever language it was last
// (re)generated in — independent viewers can refresh the same city in
// different languages, so the one on screen may not match the viewer's own
// active UI language. Surfaced as a small badge rather than silently
// showing (e.g.) an English summary while browsing in French.
const briefLanguageLabel = computed(() => {
  if (!brief.value) return null
  return SUPPORTED_LOCALES.find((l) => l.code === brief.value?.language)?.label ?? brief.value.language
})
const briefLanguageMismatch = computed(() => !!brief.value && brief.value.language !== locale.value)

const status = ref<AIIntelligenceStatus | null>(null)
const brief = ref<SituationBrief | null>(null)
const loading = ref(true)
const refreshing = ref(false)
const refreshMessage = ref<string | null>(null)

// Live countdown to the next scheduled analysis — purely a display tick,
// never drives a fetch itself (the P3 gate is "no unnecessary LLM call on
// dashboard load": this page polls its own status/brief periodically, but
// only the scheduler/manual button ever call the AI provider).
const now = ref(Date.now())
let countdownTimer: ReturnType<typeof setInterval> | undefined
let pollTimer: ReturnType<typeof setInterval> | undefined

async function load(): Promise<void> {
  loading.value = true
  try {
    const [statusResp, briefResp] = await Promise.all([
      fetchIntelligenceStatus(),
      fetchLatestBrief(cityStore.selectedCityId),
    ])
    status.value = statusResp
    brief.value = briefResp
  } finally {
    loading.value = false
  }
}

async function handleRefresh(): Promise<void> {
  refreshing.value = true
  refreshMessage.value = null
  try {
    const result = await triggerAnalysis(locale.value, cityStore.selectedCityId)
    if (result.ok && result.brief) {
      brief.value = result.brief
    } else if (!result.ok) {
      refreshMessage.value = result.message
    }
    status.value = await fetchIntelligenceStatus()
  } finally {
    refreshing.value = false
  }
}

// Reload when the header's city selector changes — same pattern as the
// main dashboard (CommandCenterView.vue).
watch(() => cityStore.selectedCityId, load)

const countdownLabel = computed(() => {
  if (!status.value?.next_analysis_at) return null
  const diffMs = new Date(status.value.next_analysis_at).getTime() - now.value
  if (diffMs <= 0) return t('intelligence.status.dueNow')
  const totalSeconds = Math.floor(diffMs / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}m ${seconds.toString().padStart(2, '0')}s`
})

onMounted(() => {
  load()
  countdownTimer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
  // Light polling so this page reflects a scheduler-generated brief without
  // requiring a manual reload — well within "no per-load LLM call" since
  // this only re-reads what's already stored, it never triggers generation.
  pollTimer = setInterval(load, 60000)
})
onUnmounted(() => {
  if (countdownTimer) clearInterval(countdownTimer)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div>
    <v-card
      variant="flat"
      border
      class="mb-4 pa-4"
    >
      <div class="d-flex align-center ga-3 flex-wrap">
        <v-progress-circular
          v-if="loading"
          indeterminate
          size="20"
          color="primary"
        />
        <template v-else>
          <v-chip
            :color="status?.is_configured ? 'success' : 'warning'"
            size="small"
            variant="flat"
          >
            <v-icon
              start
              icon="mdi-circle"
              size="10"
            />
            {{ status?.is_configured ? t('intelligence.status.active') : t('intelligence.status.disabled') }}
          </v-chip>

          <span class="text-body-2 text-medium-emphasis">
            {{ t('intelligence.status.lastAnalysis') }}:
            {{ brief ? new Date(brief.generated_at).toLocaleString() : t('intelligence.status.never') }}
          </span>

          <span
            v-if="status?.is_configured"
            class="text-body-2 text-medium-emphasis"
          >
            {{ t('intelligence.status.countdown') }}: {{ countdownLabel ?? '—' }}
          </span>

          <span
            v-if="status?.is_configured"
            class="text-body-2 text-medium-emphasis"
          >
            {{ t('intelligence.status.requestsToday') }}: {{ status.requests_today }}/{{ status.daily_request_ceiling }}
          </span>

          <v-spacer />

          <v-btn
            v-if="canExecute && status?.is_configured"
            size="small"
            variant="tonal"
            color="primary"
            :loading="refreshing"
            prepend-icon="mdi-refresh"
            @click="handleRefresh"
          >
            {{ t('intelligence.status.refresh') }}
          </v-btn>
          <v-btn
            v-else-if="!status?.is_configured"
            size="small"
            variant="text"
            color="primary"
            :to="{ name: 'settings', query: { tab: 'ai-provider' } }"
          >
            {{ t('intelligence.status.configureLink') }}
          </v-btn>
        </template>
      </div>

      <v-alert
        v-if="status?.last_analysis_error"
        type="warning"
        variant="tonal"
        density="compact"
        class="mt-3"
      >
        {{ t('intelligence.status.errorPrefix') }} {{ status.last_analysis_error }}
      </v-alert>
      <v-alert
        v-if="refreshMessage"
        type="info"
        variant="tonal"
        density="compact"
        class="mt-3"
      >
        {{ refreshMessage }}
      </v-alert>
    </v-card>

    <v-card
      v-if="!loading && !brief"
      variant="flat"
      border
      class="pa-8 d-flex flex-column align-center justify-center text-center"
    >
      <v-icon
        icon="mdi-creation-outline"
        size="48"
        color="medium-emphasis"
        class="mb-3"
      />
      <p class="text-body-1 text-medium-emphasis mb-1">
        {{ status?.is_configured ? t('intelligence.emptyForCity', { city: cityLabel }) : t('intelligence.empty') }}
      </p>
      <v-btn
        v-if="!status?.is_configured"
        variant="text"
        color="primary"
        :to="{ name: 'settings', query: { tab: 'ai-provider' } }"
      >
        {{ t('nav.settings') }}
      </v-btn>
    </v-card>

    <v-card
      v-else-if="brief"
      variant="flat"
      border
      class="pa-4"
    >
      <div class="d-flex align-center ga-3 flex-wrap mb-3">
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
      </div>

      <p class="text-body-1 mb-4">
        {{ brief.summary }}
      </p>

      <v-row>
        <v-col
          v-if="brief.drivers.length"
          cols="12"
          md="4"
        >
          <div class="text-subtitle-2 mb-1">
            {{ t('intelligence.brief.drivers') }}
          </div>
          <ul class="text-body-2 text-medium-emphasis pl-4">
            <li
              v-for="(item, i) in brief.drivers"
              :key="i"
            >
              {{ item }}
            </li>
          </ul>
        </v-col>
        <v-col
          v-if="brief.zones_to_watch.length"
          cols="12"
          md="4"
        >
          <div class="text-subtitle-2 mb-1">
            {{ t('intelligence.brief.zonesToWatch') }}
          </div>
          <ul class="text-body-2 text-medium-emphasis pl-4">
            <li
              v-for="(item, i) in brief.zones_to_watch"
              :key="i"
            >
              {{ item }}
            </li>
          </ul>
        </v-col>
        <v-col
          v-if="brief.recommendations.length"
          cols="12"
          md="4"
        >
          <div class="text-subtitle-2 mb-1">
            {{ t('intelligence.brief.recommendations') }}
          </div>
          <ul class="text-body-2 text-medium-emphasis pl-4">
            <li
              v-for="(item, i) in brief.recommendations"
              :key="i"
            >
              {{ item }}
            </li>
          </ul>
        </v-col>
      </v-row>

      <v-divider
        v-if="brief.limitations.length"
        class="my-3"
      />
      <div
        v-if="brief.limitations.length"
        class="mb-2"
      >
        <div class="text-subtitle-2 mb-1">
          {{ t('intelligence.brief.limitations') }}
        </div>
        <ul class="text-body-2 text-medium-emphasis pl-4">
          <li
            v-for="(item, i) in brief.limitations"
            :key="i"
          >
            {{ item }}
          </li>
        </ul>
      </div>

      <v-divider class="my-3" />
      <div class="text-caption text-medium-emphasis">
        {{ t('intelligence.brief.generatedBy') }} {{ brief.provider }} · {{ brief.model }} ·
        {{ t(`intelligence.brief.triggeredBy.${brief.triggered_by}`) }} ·
        {{ new Date(brief.generated_at).toLocaleString() }}
      </div>
    </v-card>
  </div>
</template>
