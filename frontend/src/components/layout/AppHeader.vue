<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { api } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { SUPPORTED_LOCALES, setLocale, type AppLocale } from '@/i18n'

const props = defineProps<{ compact?: boolean }>()

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const uiStore = useUiStore()

const systemOnline = ref(true)
let healthTimer: ReturnType<typeof setInterval> | undefined

async function pollHealth(): Promise<void> {
  try {
    const resp = await api.get('/health/ready')
    systemOnline.value = resp.data.status === 'ok'
  } catch {
    systemOnline.value = false
  }
}

onMounted(() => {
  pollHealth()
  healthTimer = setInterval(pollHealth, 30000)
})
onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer)
})

const initials = computed(() => {
  const name = authStore.currentUser?.full_name || authStore.currentUser?.email || ''
  return name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
})

function onLocaleChange(code: AppLocale): void {
  setLocale(code)
}

async function onLogout(): Promise<void> {
  await authStore.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <v-app-bar
    :density="props.compact ? 'compact' : 'default'"
    elevation="1"
    color="surface"
  >
    <template #prepend>
      <v-app-bar-nav-icon
        v-if="!props.compact"
        :icon="uiStore.sidebarCollapsed ? 'mdi-menu' : 'mdi-menu-open'"
        :aria-label="uiStore.sidebarCollapsed ? t('nav.expand') : t('nav.collapse')"
        @click="uiStore.toggleSidebar()"
      />
    </template>

    <v-app-bar-title class="d-flex align-center ga-2">
      <span class="font-weight-bold">{{ t('common.appName') }}</span>
      <span class="text-medium-emphasis d-none d-sm-inline">| Toulouse Métropole</span>
      <v-chip
        size="small"
        :color="systemOnline ? 'success' : 'error'"
        variant="flat"
        class="ml-2"
        data-testid="system-status-chip"
      >
        <v-icon
          start
          icon="mdi-circle"
          size="10"
        />
        {{ systemOnline ? t('common.status.ok') : t('common.status.degraded') }}
      </v-chip>
    </v-app-bar-title>

    <template #append>
      <v-menu>
        <template #activator="{ props: menuProps }">
          <v-btn
            v-bind="menuProps"
            icon="mdi-web"
            :aria-label="t('common.language')"
          />
        </template>
        <v-list>
          <v-list-item
            v-for="opt in SUPPORTED_LOCALES"
            :key="opt.code"
            :active="locale === opt.code"
            @click="onLocaleChange(opt.code)"
          >
            <v-list-item-title>{{ opt.label }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>

      <v-btn
        :icon="uiStore.isDark ? 'mdi-weather-sunny' : 'mdi-weather-night'"
        :aria-label="t('common.theme.toggle')"
        @click="uiStore.toggleTheme()"
      />

      <v-btn
        :icon="uiStore.monitoringFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'"
        :aria-label="uiStore.monitoringFullscreen ? t('common.fullscreen.exit') : t('common.fullscreen.enter')"
        @click="uiStore.monitoringFullscreen ? uiStore.exitMonitoringFullscreen() : uiStore.enterMonitoringFullscreen()"
      />

      <v-menu>
        <template #activator="{ props: menuProps }">
          <v-btn
            v-bind="menuProps"
            icon="mdi-bell-outline"
            :aria-label="t('common.notifications')"
          />
        </template>
        <v-card min-width="280">
          <v-card-text class="text-medium-emphasis text-center py-6">
            {{ t('common.status.empty') }}
          </v-card-text>
        </v-card>
      </v-menu>

      <v-menu>
        <template #activator="{ props: menuProps }">
          <v-btn
            v-bind="menuProps"
            variant="text"
            class="text-none"
          >
            <v-avatar
              size="32"
              color="primary"
              class="mr-2"
            >
              <span class="text-caption font-weight-bold">{{ initials }}</span>
            </v-avatar>
            <span class="d-none d-md-inline">{{ authStore.currentUser?.full_name }}</span>
          </v-btn>
        </template>
        <v-list min-width="220">
          <v-list-item :subtitle="authStore.currentUser?.email">
            <v-list-item-title>{{ authStore.currentUser?.roles?.[0]?.name }}</v-list-item-title>
          </v-list-item>
          <v-divider />
          <v-list-item
            prepend-icon="mdi-logout"
            :title="t('common.logout')"
            @click="onLogout"
          />
        </v-list>
      </v-menu>
    </template>
  </v-app-bar>
</template>
