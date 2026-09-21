<script setup lang="ts">
import { computed } from 'vue'

import { useUiStore } from '@/stores/ui'

const props = withDefaults(
  defineProps<{
    widgetId: string
    title: string
    loading?: boolean
    error?: string | null
    empty?: boolean
    emptyText?: string
    allowFullscreen?: boolean
    minHeight?: string | number
  }>(),
  {
    loading: false,
    error: null,
    empty: false,
    emptyText: '',
    allowFullscreen: true,
    minHeight: 320,
  },
)

const uiStore = useUiStore()

const isFullscreen = computed(() => uiStore.widgetFullscreenId === props.widgetId)

function toggleFullscreen(): void {
  uiStore.toggleWidgetFullscreen(props.widgetId)
}
</script>

<template>
  <v-card
    :class="['d-flex flex-column', { 'aq-monitoring-fullscreen pa-4': isFullscreen }]"
    :style="!isFullscreen ? { minHeight: typeof minHeight === 'number' ? `${minHeight}px` : minHeight } : undefined"
    variant="flat"
    border
  >
    <v-card-item>
      <template #append>
        <v-btn
          v-if="allowFullscreen"
          size="small"
          variant="text"
          :icon="isFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'"
          @click="toggleFullscreen"
        />
      </template>
      <v-card-title class="text-subtitle-1 font-weight-bold">
        {{ title }}
      </v-card-title>
    </v-card-item>

    <v-card-text class="flex-grow-1 d-flex flex-column">
      <div
        v-if="loading"
        class="flex-grow-1 d-flex align-center justify-center"
      >
        <v-progress-circular
          indeterminate
          color="primary"
        />
      </div>
      <div
        v-else-if="error"
        class="flex-grow-1 d-flex flex-column align-center justify-center text-error"
      >
        <v-icon
          icon="mdi-alert-circle-outline"
          size="32"
          class="mb-2"
        />
        <span class="text-body-2">{{ error }}</span>
      </div>
      <div
        v-else-if="empty"
        class="flex-grow-1 d-flex flex-column align-center justify-center text-medium-emphasis"
      >
        <v-icon
          icon="mdi-database-off-outline"
          size="32"
          class="mb-2"
        />
        <span class="text-body-2 text-center">{{ emptyText }}</span>
      </div>
      <div
        v-else
        class="flex-grow-1 d-flex flex-column"
      >
        <slot />
      </div>
    </v-card-text>
  </v-card>
</template>
