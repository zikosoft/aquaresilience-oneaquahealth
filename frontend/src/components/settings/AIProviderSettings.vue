<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api, extractApiErrorMessage } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type { AIProviderConfig, AIProviderConfigUpdate } from '@/types'

const { t } = useI18n()
const authStore = useAuthStore()
const canEdit = computed(() => authStore.can('SETTINGS', 'EDIT'))

const providerOptions = [
  { value: 'openai', title: 'OpenAI' },
  { value: 'anthropic', title: 'Anthropic' },
]

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const testResult = ref<{ ok: boolean; message: string } | null>(null)
const isConfigured = ref(false)
const showApiKey = ref(false)

const form = reactive<AIProviderConfigUpdate>({
  provider: 'openai',
  model: '',
  api_key: '',
  max_output_tokens: 1024,
  scheduled_analysis_interval_minutes: 240,
  daily_request_ceiling: 6,
  event_triggered_enabled: false,
  cooldown_seconds: 900,
})

async function load(): Promise<void> {
  loading.value = true
  try {
    const resp = await api.get<AIProviderConfig>('/settings/ai-provider/config')
    const data = resp.data
    form.provider = data.provider
    form.model = data.model
    form.max_output_tokens = data.max_output_tokens
    form.scheduled_analysis_interval_minutes = data.scheduled_analysis_interval_minutes
    form.daily_request_ceiling = data.daily_request_ceiling
    form.event_triggered_enabled = data.event_triggered_enabled
    form.cooldown_seconds = data.cooldown_seconds
    isConfigured.value = data.is_configured
  } catch (err) {
    errorMessage.value = extractApiErrorMessage(err, t('common.status.error'))
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  saving.value = true
  errorMessage.value = null
  successMessage.value = null
  try {
    const payload: AIProviderConfigUpdate = { ...form }
    if (!payload.api_key) delete payload.api_key
    const resp = await api.put<AIProviderConfig>('/settings/ai-provider/config', payload)
    isConfigured.value = resp.data.is_configured
    form.api_key = ''
    successMessage.value = t('settings.aiProvider.saved')
  } catch (err) {
    errorMessage.value = extractApiErrorMessage(err, t('common.status.error'))
  } finally {
    saving.value = false
  }
}

async function testConnection(): Promise<void> {
  testing.value = true
  testResult.value = null
  try {
    const resp = await api.post<{ ok: boolean; message: string }>('/settings/ai-provider/test')
    testResult.value = resp.data
  } catch (err) {
    testResult.value = { ok: false, message: extractApiErrorMessage(err, t('settings.aiProvider.testFailure')) }
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>

<template>
  <v-card
    variant="flat"
    border
  >
    <v-card-item>
      <v-card-title class="text-subtitle-1 font-weight-bold">
        {{ t('settings.tabs.aiProvider') }}
      </v-card-title>
      <template #append>
        <v-chip
          :color="isConfigured ? 'success' : 'warning'"
          size="small"
          variant="flat"
        >
          {{ isConfigured ? t('settings.aiProvider.configured') : t('settings.aiProvider.notConfigured') }}
        </v-chip>
      </template>
    </v-card-item>
    <v-card-text>
      <div
        v-if="loading"
        class="d-flex justify-center py-6"
      >
        <v-progress-circular
          indeterminate
          color="primary"
        />
      </div>
      <template v-else>
        <v-alert
          v-if="errorMessage"
          type="error"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          {{ errorMessage }}
        </v-alert>
        <v-alert
          v-if="successMessage"
          type="success"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          {{ successMessage }}
        </v-alert>
        <v-alert
          v-if="testResult"
          :type="testResult.ok ? 'success' : 'error'"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          {{ testResult.message }}
        </v-alert>

        <v-row dense>
          <v-col
            cols="12"
            sm="6"
          >
            <v-select
              v-model="form.provider"
              :items="providerOptions"
              item-title="title"
              item-value="value"
              :label="t('settings.aiProvider.provider')"
              :disabled="!canEdit"
            />
          </v-col>
          <v-col
            cols="12"
            sm="6"
          >
            <v-text-field
              v-model="form.model"
              :label="t('settings.aiProvider.model')"
              :disabled="!canEdit"
            />
          </v-col>
          <v-col cols="12">
            <v-text-field
              v-model="form.api_key"
              :label="t('settings.aiProvider.apiKey')"
              :hint="t('settings.aiProvider.apiKeyHint')"
              persistent-hint
              :type="showApiKey ? 'text' : 'password'"
              :append-inner-icon="showApiKey ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
              autocomplete="new-password"
              :disabled="!canEdit"
              @click:append-inner="showApiKey = !showApiKey"
            />
          </v-col>
          <v-col
            cols="12"
            sm="6"
          >
            <v-text-field
              v-model.number="form.max_output_tokens"
              type="number"
              :label="t('settings.aiProvider.maxOutputTokens')"
              :disabled="!canEdit"
            />
          </v-col>
          <v-col
            cols="12"
            sm="6"
          >
            <v-text-field
              v-model.number="form.scheduled_analysis_interval_minutes"
              type="number"
              :label="t('settings.aiProvider.scheduledInterval')"
              :disabled="!canEdit"
            />
          </v-col>
          <v-col
            cols="12"
            sm="6"
          >
            <v-text-field
              v-model.number="form.daily_request_ceiling"
              type="number"
              :label="t('settings.aiProvider.dailyCeiling')"
              :disabled="!canEdit"
            />
          </v-col>
          <v-col
            cols="12"
            sm="6"
          >
            <v-text-field
              v-model.number="form.cooldown_seconds"
              type="number"
              :label="t('settings.aiProvider.cooldown')"
              :disabled="!canEdit"
            />
          </v-col>
          <v-col cols="12">
            <v-switch
              v-model="form.event_triggered_enabled"
              :label="t('settings.aiProvider.eventTriggered')"
              color="primary"
              :disabled="!canEdit"
            />
          </v-col>
        </v-row>
      </template>
    </v-card-text>
    <v-card-actions v-if="canEdit && !loading">
      <v-btn
        variant="outlined"
        :loading="testing"
        :disabled="!isConfigured"
        @click="testConnection"
      >
        {{ t('settings.aiProvider.testConnection') }}
      </v-btn>
      <v-spacer />
      <v-btn
        color="primary"
        :loading="saving"
        @click="save"
      >
        {{ t('settings.aiProvider.save') }}
      </v-btn>
    </v-card-actions>
  </v-card>
</template>
