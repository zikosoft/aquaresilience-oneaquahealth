<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/services/api'
import type { AIProviderConfig } from '@/types'

const { t } = useI18n()

const config = ref<AIProviderConfig | null>(null)
const loading = ref(true)

async function loadConfig(): Promise<void> {
  loading.value = true
  try {
    const resp = await api.get<AIProviderConfig>('/settings/ai-provider/config')
    config.value = resp.data
  } catch {
    config.value = null
  } finally {
    loading.value = false
  }
}

onMounted(loadConfig)
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
            :color="config?.is_configured ? 'success' : 'warning'"
            size="small"
            variant="flat"
          >
            <v-icon
              start
              icon="mdi-circle"
              size="10"
            />
            {{ config?.is_configured ? t('intelligence.status.active') : t('intelligence.status.disabled') }}
          </v-chip>
          <span
            v-if="config"
            class="text-body-2 text-medium-emphasis"
          >
            {{ config.provider }} · {{ config.model || '—' }}
          </span>
        </template>
      </div>
    </v-card>

    <v-card
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
        {{ t('intelligence.empty') }}
      </p>
      <v-btn
        v-if="!config?.is_configured"
        variant="text"
        color="primary"
        :to="{ name: 'settings', query: { tab: 'ai-provider' } }"
      >
        {{ t('nav.settings') }}
      </v-btn>
    </v-card>
  </div>
</template>
