<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import { useUiStore } from '@/stores/ui'

const uiStore = useUiStore()

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && uiStore.monitoringFullscreen) {
    uiStore.exitMonitoringFullscreen()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div :class="{ 'aq-monitoring-fullscreen': uiStore.monitoringFullscreen }">
    <AppSidebar v-if="!uiStore.monitoringFullscreen" />
    <AppHeader :compact="uiStore.monitoringFullscreen" />
    <v-main>
      <v-container
        fluid
        class="pa-4 pa-md-6"
      >
        <router-view />
      </v-container>
    </v-main>
  </div>
</template>
