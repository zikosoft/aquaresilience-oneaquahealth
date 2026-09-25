<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import SourceHealthBadge from '@/components/common/SourceHealthBadge.vue'
import { extractApiErrorMessage } from '@/services/api'
import { fetchSources, updateSourceCredentials } from '@/services/environmentalApi'
import { useAuthStore } from '@/stores/auth'
import type { SourceCityRef, SourceHealth } from '@/types'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const canEdit = computed(() => authStore.can('DATA_SOURCES', 'EDIT'))

const loading = ref(true)
const errorMessage = ref<string | null>(null)
const sources = ref<SourceHealth[]>([])

const headers = [
  { title: t('sources.table.name'), key: 'name' },
  { title: t('sources.table.category'), key: 'kind' },
  { title: t('sources.table.status'), key: 'health' },
  { title: t('sources.table.lastSync'), key: 'last_success_at' },
  { title: t('sources.license'), key: 'license' },
  { title: '', key: 'credentials', sortable: false, width: 1 },
]

// Session 020 (user request): group by city instead of a flat list, using
// the same {code -> label_en/fr/es} localization pattern AppHeader.vue's
// city selector already uses, so this stays correct for every enabled
// locale without any per-language code here.
function cityLabel(city: SourceCityRef): string {
  const byLocale: Record<string, string> = { en: city.label_en, fr: city.label_fr, es: city.label_es }
  return byLocale[locale.value] ?? city.label_en
}

interface SourceGroup {
  key: string
  label: string
  sources: SourceHealth[]
}

const groups = computed<SourceGroup[]>(() => {
  const byCity = new Map<string, SourceGroup>()
  for (const source of sources.value) {
    const key = source.city?.id ?? '__unassigned__'
    const label = source.city ? cityLabel(source.city) : t('sources.unassignedCity')
    if (!byCity.has(key)) byCity.set(key, { key, label, sources: [] })
    byCity.get(key)!.sources.push(source)
  }
  // Toulouse (the one demo-live city) first, then alphabetically — purely
  // cosmetic ordering, has no bearing on which cities have real data.
  return [...byCity.values()].sort((a, b) => {
    if (a.label === 'Toulouse') return -1
    if (b.label === 'Toulouse') return 1
    return a.label.localeCompare(b.label)
  })
})

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

// --- Session 020: write-only "add API key" dialog, one source at a time —
// same encrypted-at-rest, never-echoed-back pattern as the Settings > AI
// Provider page (components/settings/AIProviderSettings.vue).
const credentialsDialog = reactive({
  open: false,
  source: null as SourceHealth | null,
  apiKey: '',
  showKey: false,
  saving: false,
  error: null as string | null,
})

function openCredentialsDialog(source: SourceHealth): void {
  credentialsDialog.open = true
  credentialsDialog.source = source
  credentialsDialog.apiKey = ''
  credentialsDialog.showKey = false
  credentialsDialog.error = null
}

async function saveCredentials(): Promise<void> {
  if (!credentialsDialog.source || !credentialsDialog.apiKey) return
  credentialsDialog.saving = true
  credentialsDialog.error = null
  try {
    const updated = await updateSourceCredentials(credentialsDialog.source.id, credentialsDialog.apiKey)
    const index = sources.value.findIndex((s) => s.id === updated.id)
    if (index !== -1) sources.value[index] = updated
    credentialsDialog.open = false
  } catch (e) {
    credentialsDialog.error = extractApiErrorMessage(e, t('common.status.error'))
  } finally {
    credentialsDialog.saving = false
  }
}
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

    <div
      v-if="loading"
      class="d-flex justify-center py-8"
    >
      <v-progress-circular
        indeterminate
        color="primary"
      />
    </div>

    <template v-else>
      <v-card
        v-if="sources.length === 0"
        variant="flat"
        border
      >
        <v-card-text class="text-medium-emphasis">
          {{ t('sources.empty') }}
        </v-card-text>
      </v-card>

      <v-card
        v-for="group in groups"
        :key="group.key"
        variant="flat"
        border
        class="mb-4"
      >
        <v-card-item>
          <v-card-title class="text-subtitle-1 font-weight-bold d-flex align-center">
            <v-icon
              icon="mdi-map-marker-outline"
              size="small"
              class="mr-1"
            />
            {{ group.label }}
            <v-chip
              size="x-small"
              variant="tonal"
              class="ml-2"
            >
              {{ group.sources.length }}
            </v-chip>
          </v-card-title>
        </v-card-item>

        <v-data-table
          :headers="headers"
          :items="group.sources"
          :items-per-page="-1"
          hide-default-footer
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
          <template #item.credentials="{ item }">
            <v-chip
              v-if="item.requires_api_key && item.is_key_configured"
              size="small"
              color="success"
              variant="tonal"
              prepend-icon="mdi-key-variant"
            >
              {{ t('sources.credentials.configured') }}
            </v-chip>
            <v-btn
              v-else-if="item.requires_api_key && canEdit"
              size="small"
              variant="outlined"
              color="warning"
              prepend-icon="mdi-key-plus"
              @click="openCredentialsDialog(item)"
            >
              {{ t('sources.credentials.addKey') }}
            </v-btn>
            <v-chip
              v-else-if="item.requires_api_key"
              size="small"
              color="warning"
              variant="tonal"
            >
              {{ t('sources.credentials.missing') }}
            </v-chip>
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
    </template>

    <v-dialog
      v-model="credentialsDialog.open"
      max-width="480"
    >
      <v-card v-if="credentialsDialog.source">
        <v-card-title>{{ t('sources.credentials.dialogTitle', { name: credentialsDialog.source.name }) }}</v-card-title>
        <v-card-text>
          <p class="text-body-2 text-medium-emphasis mb-3">
            {{ t('sources.credentials.dialogHint') }}
          </p>
          <v-alert
            v-if="credentialsDialog.error"
            type="error"
            variant="tonal"
            density="compact"
            class="mb-3"
          >
            {{ credentialsDialog.error }}
          </v-alert>
          <v-text-field
            v-model="credentialsDialog.apiKey"
            :label="t('sources.credentials.apiKey')"
            :type="credentialsDialog.showKey ? 'text' : 'password'"
            :append-inner-icon="credentialsDialog.showKey ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
            autocomplete="new-password"
            autofocus
            @click:append-inner="credentialsDialog.showKey = !credentialsDialog.showKey"
          />
          <a
            v-if="credentialsDialog.source.homepage_url"
            :href="credentialsDialog.source.homepage_url"
            target="_blank"
            rel="noopener noreferrer"
            class="text-caption"
          >{{ t('sources.credentials.whereToGetKey') }}</a>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            variant="text"
            @click="credentialsDialog.open = false"
          >
            {{ t('common.actions.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            :loading="credentialsDialog.saving"
            :disabled="!credentialsDialog.apiKey"
            @click="saveCredentials"
          >
            {{ t('common.actions.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
