<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import SourceHealthBadge from '@/components/common/SourceHealthBadge.vue'
import { extractApiErrorMessage } from '@/services/api'
import { fetchSources } from '@/services/environmentalApi'
import type { SourceHealth } from '@/types'

const { t } = useI18n()

const loading = ref(true)
const errorMessage = ref<string | null>(null)
const sources = ref<SourceHealth[]>([])

const headers = [
  { title: t('sources.table.name'), key: 'name' },
  { title: t('sources.table.category'), key: 'kind' },
  { title: t('sources.table.status'), key: 'health' },
  { title: t('sources.table.lastSync'), key: 'last_success_at' },
  { title: t('sources.license'), key: 'license' },
]

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    sources.value = await fetchSources()
  } catch (e) {
    errorMessage.value = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    loading.value = false
  }
}

onMounted(load)
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

    <v-card
      variant="flat"
      border
    >
      <v-data-table
        :headers="headers"
        :items="sources"
        :loading="loading"
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

    <v-alert
      v-for="source in sources.filter((s) => s.last_error_message)"
      :key="source.id"
      type="warning"
      variant="tonal"
      density="compact"
      class="mt-2"
    >
      <strong>{{ source.name }}</strong> — {{ t('sources.lastError') }}: {{ source.last_error_message }}
    </v-alert>
  </div>
</template>
