<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractApiErrorMessage } from '@/services/api'
import { trackEvent } from '@/services/analytics'
import { acknowledgeWarning, fetchWarnings, resolveWarning } from '@/services/riskApi'
import { useAuthStore } from '@/stores/auth'
import { useCityStore } from '@/stores/city'
import type { EarlyWarning } from '@/types'
import { factorTranslationKey, leadingFactorKey, severityColor } from '@/utils/risk'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const cityStore = useCityStore()

const cityTracksWarnings = computed(() => cityStore.selectedCity?.is_primary ?? true)
const cityLabel = computed(() => {
  const city = cityStore.selectedCity
  if (!city) return ''
  const byLocale: Record<string, string> = { en: city.label_en, fr: city.label_fr, es: city.label_es }
  return byLocale[locale.value] ?? city.label_en
})

// i18n: rebuild the warning sentence client-side from structured fields
// instead of displaying the backend's pre-rendered English message.
function warningMessage(warning: EarlyWarning): string {
  const factorKey = leadingFactorKey(warning.factors)
  return t('alerts.message', {
    score: warning.risk_score,
    severity: t(`alerts.severity.${warning.severity.toLowerCase()}`),
    factor: factorKey ? t(factorTranslationKey(factorKey)) : '—',
  })
}

const lifecycleSteps = ['active', 'acknowledged', 'resolved'] as const

const loading = ref(true)
const errorMessage = ref<string | null>(null)
const warnings = ref<EarlyWarning[]>([])
// Tracks which single warning's Acknowledge/Resolve button is mid-request,
// so only that row's button shows a spinner (a list can have several
// resolved/historical rows alongside the one currently open).
const actionLoadingId = ref<string | null>(null)

const canEdit = computed(() => authStore.can('ALERTS', 'EDIT'))
const canExecute = computed(() => authStore.can('ALERTS', 'EXECUTE'))

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    warnings.value = await fetchWarnings()
  } catch (e) {
    errorMessage.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function onAcknowledge(id: string): Promise<void> {
  actionLoadingId.value = id
  errorMessage.value = null
  try {
    await acknowledgeWarning(id)
    trackEvent('warning_acknowledged')
    await load()
  } catch (e) {
    errorMessage.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    actionLoadingId.value = null
  }
}

async function onResolve(id: string): Promise<void> {
  actionLoadingId.value = id
  errorMessage.value = null
  try {
    await resolveWarning(id)
    trackEvent('warning_resolved')
    await load()
  } catch (e) {
    errorMessage.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    actionLoadingId.value = null
  }
}
</script>

<template>
  <div>
    <v-card
      variant="flat"
      border
      class="mb-4 pa-4"
    >
      <div class="d-flex flex-wrap ga-2 align-center">
        <span class="text-body-2 text-medium-emphasis mr-2">{{ t('alerts.title') }}:</span>
        <template
          v-for="(step, idx) in lifecycleSteps"
          :key="step"
        >
          <v-chip
            size="small"
            variant="outlined"
          >
            {{ t(`alerts.lifecycle.${step}`) }}
          </v-chip>
          <v-icon
            v-if="idx < lifecycleSteps.length - 1"
            icon="mdi-arrow-right"
            size="16"
            class="text-medium-emphasis"
          />
        </template>
      </div>
    </v-card>

    <v-alert
      v-if="!cityTracksWarnings"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      {{ t('alerts.primaryCityNotice', { city: cityLabel }) }}
    </v-alert>

    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      {{ errorMessage }}
    </v-alert>

    <div
      v-if="loading"
      class="d-flex justify-center py-8"
    >
      <v-progress-circular
        indeterminate
        color="primary"
      />
    </div>

    <v-card
      v-else-if="warnings.length === 0"
      variant="flat"
      border
      class="pa-8 d-flex flex-column align-center justify-center text-center"
    >
      <v-icon
        icon="mdi-bell-check-outline"
        size="48"
        color="medium-emphasis"
        class="mb-3"
      />
      <p class="text-body-1 text-medium-emphasis">
        {{ t('alerts.empty') }}
      </p>
    </v-card>

    <v-row
      v-else
      dense
    >
      <v-col
        v-for="warning in warnings"
        :key="warning.id"
        cols="12"
      >
        <v-card
          variant="flat"
          border
          class="pa-4"
        >
          <div class="d-flex flex-wrap align-center justify-space-between ga-2 mb-2">
            <div class="d-flex align-center ga-2 flex-wrap">
              <v-chip
                :color="severityColor(warning.severity)"
                size="small"
                variant="flat"
              >
                {{ t(`alerts.severity.${warning.severity.toLowerCase()}`) }}
              </v-chip>
              <v-chip
                size="small"
                variant="outlined"
              >
                {{ t(`alerts.lifecycle.${warning.status.toLowerCase()}`) }}
              </v-chip>
              <span class="text-caption text-medium-emphasis">
                {{ t('alerts.score', { score: warning.risk_score }) }}
              </span>
            </div>
            <div class="d-flex ga-2">
              <v-btn
                v-if="warning.status === 'ACTIVE' && canEdit"
                size="small"
                variant="tonal"
                :loading="actionLoadingId === warning.id"
                @click="onAcknowledge(warning.id)"
              >
                {{ t('alerts.actions.acknowledge') }}
              </v-btn>
              <v-btn
                v-if="warning.status !== 'RESOLVED' && canExecute"
                size="small"
                variant="tonal"
                color="primary"
                :loading="actionLoadingId === warning.id"
                @click="onResolve(warning.id)"
              >
                {{ t('alerts.actions.resolve') }}
              </v-btn>
            </div>
          </div>

          <p class="text-body-2 mb-2">
            {{ warningMessage(warning) }}
          </p>

          <div class="d-flex flex-wrap ga-4 text-caption text-medium-emphasis">
            <span>{{ t('alerts.triggeredAt', { time: new Date(warning.triggered_at).toLocaleString() }) }}</span>
            <span v-if="warning.acknowledged_at">
              {{
                t('alerts.acknowledgedAt', {
                  time: new Date(warning.acknowledged_at).toLocaleString(),
                  name: warning.acknowledged_by,
                })
              }}
            </span>
            <span v-if="warning.resolved_at">
              {{
                t('alerts.resolvedAt', {
                  time: new Date(warning.resolved_at).toLocaleString(),
                  name: warning.resolved_by,
                })
              }}
            </span>
          </div>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>
