import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

type ThemeMode = 'light' | 'dark'

const SIDEBAR_KEY = 'aquaresilience.sidebar_collapsed'
const THEME_KEY = 'aquaresilience.theme'

function readStoredTheme(): ThemeMode {
  const stored = localStorage.getItem(THEME_KEY) as ThemeMode | null
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const useUiStore = defineStore('ui', () => {
  const sidebarCollapsed = ref<boolean>(localStorage.getItem(SIDEBAR_KEY) === '1')
  const themeMode = ref<ThemeMode>(readStoredTheme())
  const monitoringFullscreen = ref(false)
  const widgetFullscreenId = ref<string | null>(null)

  const isDark = computed(() => themeMode.value === 'dark')

  watch(sidebarCollapsed, (value) => {
    localStorage.setItem(SIDEBAR_KEY, value ? '1' : '0')
  })
  watch(themeMode, (value) => {
    localStorage.setItem(THEME_KEY, value)
  })

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function toggleTheme(): void {
    themeMode.value = themeMode.value === 'dark' ? 'light' : 'dark'
  }

  function enterMonitoringFullscreen(): void {
    monitoringFullscreen.value = true
  }

  function exitMonitoringFullscreen(): void {
    monitoringFullscreen.value = false
  }

  function toggleWidgetFullscreen(id: string): void {
    widgetFullscreenId.value = widgetFullscreenId.value === id ? null : id
  }

  return {
    sidebarCollapsed,
    themeMode,
    isDark,
    monitoringFullscreen,
    widgetFullscreenId,
    toggleSidebar,
    toggleTheme,
    enterMonitoringFullscreen,
    exitMonitoringFullscreen,
    toggleWidgetFullscreen,
  }
})
