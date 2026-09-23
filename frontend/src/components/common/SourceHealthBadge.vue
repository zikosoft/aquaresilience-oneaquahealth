<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { SourceHealthStatus } from '@/types'

const props = defineProps<{ health: SourceHealthStatus }>()

const { t } = useI18n()

const colorByHealth: Record<SourceHealthStatus, string> = {
  fresh: 'success',
  stale: 'warning',
  degraded: 'error',
}

const color = computed(() => colorByHealth[props.health] ?? 'error')
const label = computed(() => t(`map.health.${props.health}`))
</script>

<template>
  <v-chip
    :color="color"
    size="small"
    variant="flat"
    density="comfortable"
  >
    {{ label }}
  </v-chip>
</template>
