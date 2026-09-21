<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDisplay } from 'vuetify'

import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const { t } = useI18n()
const authStore = useAuthStore()
const uiStore = useUiStore()
const { mobile } = useDisplay()

interface NavItem {
  to: { name: string }
  icon: string
  labelKey: string
  module: string
}

const navItems: NavItem[] = [
  { to: { name: 'dashboard' }, icon: 'mdi-view-dashboard-outline', labelKey: 'nav.dashboard', module: 'DASHBOARD' },
  { to: { name: 'map' }, icon: 'mdi-map-outline', labelKey: 'nav.map', module: 'MAP' },
  { to: { name: 'alerts' }, icon: 'mdi-alert-outline', labelKey: 'nav.alerts', module: 'ALERTS' },
  {
    to: { name: 'intelligence' },
    icon: 'mdi-creation-outline',
    labelKey: 'nav.aiIntelligence',
    module: 'AI_INTELLIGENCE',
  },
  { to: { name: 'scenarios' }, icon: 'mdi-tune-variant', labelKey: 'nav.scenarios', module: 'SCENARIOS' },
  { to: { name: 'sources' }, icon: 'mdi-database-outline', labelKey: 'nav.dataSources', module: 'DATA_SOURCES' },
]

const visibleNavItems = computed(() => navItems.filter((item) => authStore.can(item.module, 'VIEW')))
const canViewSettings = computed(() => authStore.can('SETTINGS', 'VIEW'))

const railMode = computed(() => !mobile.value && uiStore.sidebarCollapsed)
</script>

<template>
  <v-navigation-drawer
    :model-value="true"
    :rail="railMode"
    :temporary="mobile"
    :permanent="!mobile"
    rail-width="72"
    width="260"
  >
    <v-list
      nav
      density="comfortable"
    >
      <v-list-item
        v-for="item in visibleNavItems"
        :key="item.labelKey"
        :to="item.to"
        :prepend-icon="item.icon"
        :title="t(item.labelKey)"
        rounded="lg"
      />

      <v-divider class="my-2" />

      <v-list-item
        v-if="canViewSettings"
        :to="{ name: 'settings' }"
        prepend-icon="mdi-cog-outline"
        :title="t('nav.settings')"
        rounded="lg"
      />
    </v-list>
  </v-navigation-drawer>
</template>
