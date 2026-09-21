<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from 'vuetify'

import { useUiStore } from '@/stores/ui'

const { locale } = useI18n()
const vuetifyTheme = useTheme()
const uiStore = useUiStore()

// The Pinia UI store is the single source of truth for light/dark mode
// (persisted to localStorage, toggled from AppHeader). Vuetify's own theme
// engine has to be told about changes explicitly via `useTheme()` — it does
// not observe app state on its own — so this keeps Vuetify's active theme
// name in sync with the store, both on load and on every toggle.
watch(
  () => uiStore.isDark,
  (dark) => {
    vuetifyTheme.global.name.value = dark ? 'dark' : 'light'
  },
  { immediate: true },
)
</script>

<template>
  <v-app :key="locale">
    <router-view />
  </v-app>
</template>
