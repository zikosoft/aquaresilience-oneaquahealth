<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api, extractApiErrorMessage } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import type { AppSetting } from '@/types'

export interface SettingFieldOption {
  value: string
  label: string
}

export interface SettingField {
  path: string // dot-path into the settings value, e.g. "weights.rainfall"
  label: string
  type: 'text' | 'number' | 'boolean' | 'select' | 'chips'
  options?: SettingFieldOption[]
  readonly?: boolean
  suffix?: string
  tooltip?: string // shown as an info icon next to the field's label
}

const props = defineProps<{
  category: string
  settingKey: string
  title: string
  description?: string
  fields: SettingField[]
}>()

const { t } = useI18n()
const authStore = useAuthStore()

const canEdit = computed(() => authStore.can('SETTINGS', 'EDIT'))

const loading = ref(true)
const saving = ref(false)
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)
// Settings values are arbitrary backend-defined JSON (each category has its
// own shape, addressed here only by dot-path strings), so an index-signature
// record of `unknown` — rather than a fully-typed interface per category —
// is the correct model, not a shortcut: `SettingField.path` is the only
// thing that ever names a piece of it.
type JsonRecord = Record<string, unknown>

function isJsonRecord(v: unknown): v is JsonRecord {
  return typeof v === 'object' && v !== null
}

const value = ref<JsonRecord>({})

function getPath(obj: JsonRecord, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, key) => (isJsonRecord(acc) ? acc[key] : undefined), obj)
}

function setPath(obj: JsonRecord, path: string, val: unknown): void {
  const keys = path.split('.')
  let cursor = obj
  for (let i = 0; i < keys.length - 1; i++) {
    const key = keys[i]
    if (!isJsonRecord(cursor[key])) cursor[key] = {}
    cursor = cursor[key] as JsonRecord
  }
  cursor[keys[keys.length - 1]] = val
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    const resp = await api.get<AppSetting[]>(`/settings/${props.category}`)
    const setting = resp.data.find((s) => s.key === props.settingKey)
    value.value = setting ? structuredClone(setting.value) : {}
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
    await api.put(`/settings/${props.category}/${props.settingKey}`, { value: value.value })
    successMessage.value = t('settings.saved')
  } catch (err) {
    errorMessage.value = extractApiErrorMessage(err, t('common.status.error'))
  } finally {
    saving.value = false
  }
}

onMounted(load)

defineExpose({ reload: load })
</script>

<template>
  <v-card
    variant="flat"
    border
  >
    <v-card-item>
      <v-card-title class="text-subtitle-1 font-weight-bold">
        {{ title }}
      </v-card-title>
      <v-card-subtitle
        v-if="description"
        class="text-wrap"
      >
        {{ description }}
      </v-card-subtitle>
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

        <v-row dense>
          <v-col
            v-for="field in fields"
            :key="field.path"
            cols="12"
            sm="6"
          >
            <v-switch
              v-if="field.type === 'boolean'"
              :model-value="getPath(value, field.path)"
              :label="field.label"
              :disabled="!canEdit || field.readonly"
              color="primary"
              @update:model-value="(v: unknown) => setPath(value, field.path, v)"
            />
            <v-select
              v-else-if="field.type === 'select'"
              :model-value="getPath(value, field.path)"
              :items="field.options"
              item-title="label"
              item-value="value"
              :label="field.label"
              :disabled="!canEdit || field.readonly"
              @update:model-value="(v: unknown) => setPath(value, field.path, v)"
            />
            <div v-else-if="field.type === 'chips'">
              <div class="text-body-2 text-medium-emphasis mb-1">
                {{ field.label }}
              </div>
              <v-chip
                v-for="item in getPath(value, field.path) || []"
                :key="item"
                size="small"
                class="mr-1 mb-1"
              >
                {{ item }}
              </v-chip>
            </div>
            <v-text-field
              v-else
              :model-value="getPath(value, field.path)"
              :type="field.type === 'number' ? 'number' : 'text'"
              :suffix="field.suffix"
              :label="field.label"
              :disabled="!canEdit || field.readonly"
              @update:model-value="(v: unknown) => setPath(value, field.path, field.type === 'number' ? Number(v) : v)"
            >
              <template
                v-if="field.tooltip"
                #append-inner
              >
                <v-tooltip
                  :text="field.tooltip"
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
              </template>
            </v-text-field>
          </v-col>
        </v-row>
      </template>
    </v-card-text>
    <v-card-actions v-if="canEdit && !loading">
      <v-spacer />
      <v-btn
        color="primary"
        :loading="saving"
        @click="save"
      >
        {{ t('common.actions.save') }}
      </v-btn>
    </v-card-actions>
  </v-card>
</template>
