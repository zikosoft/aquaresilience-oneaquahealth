<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import { useUiStore } from '@/stores/ui'

const { t } = useI18n()
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
      <!-- Session 017: Settings > System > Maintenance mode is now a real
           write-blocking gate (app/core/maintenance.py) — this banner is
           the one place that says so, set by the api.ts response
           interceptor the moment any write comes back MAINTENANCE_MODE,
           rather than every form/action across the app showing its own
           raw English error text. -->
      <v-alert
        v-if="uiStore.maintenanceModeActive"
        type="warning"
        variant="tonal"
        density="compact"
        rounded="0"
      >
        {{ t('common.maintenance.bannerMessage') }}
      </v-alert>
      <v-container
        fluid
        class="pa-4 pa-md-6"
      >
        <router-view />
      </v-container>
    </v-main>
  </div>
</template>
