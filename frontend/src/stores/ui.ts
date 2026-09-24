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
  // Session 017: flipped by the api.ts response interceptor the moment any
  // request comes back with the MAINTENANCE_MODE error code, so the whole
  // app can show one consistent banner instead of every call site having
  // to special-case this error individually. Cleared back to false as soon
  // as a write succeeds again (e.g. an Administrator having just turned it
  // back off) — see the interceptor for both sides of this.
  const maintenanceModeActive = ref(false)

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

  function setMaintenanceModeActive(value: boolean): void {
    maintenanceModeActive.value = value
  }

  return {
    sidebarCollapsed,
    themeMode,
    isDark,
    monitoringFullscreen,
    widgetFullscreenId,
    maintenanceModeActive,
    toggleSidebar,
    toggleTheme,
    enterMonitoringFullscreen,
    exitMonitoringFullscreen,
    toggleWidgetFullscreen,
    setMaintenanceModeActive,
  }
})
