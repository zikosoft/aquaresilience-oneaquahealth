<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import BrandLogo from '@/components/branding/BrandLogo.vue'
import { api } from '@/services/api'
import { trackEvent } from '@/services/analytics'
import { useAuthStore } from '@/stores/auth'
import { useCityStore } from '@/stores/city'
import { useUiStore } from '@/stores/ui'
import { SUPPORTED_LOCALES, setLocale, type AppLocale } from '@/i18n'

const props = defineProps<{ compact?: boolean }>()

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const uiStore = useUiStore()
const cityStore = useCityStore()

const logoHeight = computed(() => (props.compact ? 26 : 50))

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
  cityStore.load()
})

function cityLabel(city: { label_en: string; label_fr: string; label_es: string }): string {
  const byLocale: Record<string, string> = { en: city.label_en, fr: city.label_fr, es: city.label_es }
  return byLocale[locale.value] ?? city.label_en
}

function onCityChange(cityId: string): void {
  cityStore.selectCity(cityId)
  const city = cityStore.cities.find((c) => c.id === cityId)
  trackEvent('city_changed', { city: city?.label_en })
}

const CITY_STATUS_DOT: Record<'live' | 'pending' | 'none', string> = {
  live: '🟢',
  pending: '🟡',
  none: '⚪',
}
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
  trackEvent('logout')
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

    <v-app-bar-title>
      <div
        class="app-header-brand"
        :style="{ '--header-block-height': `${logoHeight}px` }"
      >
        <div class="app-header-logo">
          <BrandLogo
            variant="header"
            :height="logoHeight"
          />
        </div>
        <div class="app-header-context">
          <template v-if="cityStore.selectedCity">
            <div class="app-header-sep text-medium-emphasis d-none d-sm-flex">
              |
            </div>
            <div class="app-header-city text-medium-emphasis d-none d-sm-flex">
              {{ cityLabel(cityStore.selectedCity) }}
            </div>
          </template>
          <div class="app-header-status">
            <v-chip
              size="small"
              :color="systemOnline ? 'success' : 'error'"
              variant="flat"
              data-testid="system-status-chip"
            >
              <v-icon
                start
                icon="mdi-circle"
                size="10"
              />
              {{ systemOnline ? t('common.status.ok') : t('common.status.degraded') }}
            </v-chip>
          </div>
        </div>
      </div>
    </v-app-bar-title>

    <template #append>
      <v-menu v-if="cityStore.cities.length">
        <template #activator="{ props: menuProps }">
          <v-btn
            v-bind="menuProps"
            variant="text"
            class="text-none"
            :aria-label="t('common.city.select')"
          >
            <v-icon
              icon="mdi-map-marker-outline"
              start
            />
            <span class="d-none d-md-inline">{{ cityStore.selectedCity ? cityLabel(cityStore.selectedCity) : '' }}</span>
          </v-btn>
        </template>
        <v-list min-width="240">
          <v-list-item
            v-for="city in cityStore.cities"
            :key="city.id"
            :active="cityStore.selectedCityId === city.id"
            :class="{ 'opacity-60': city.connector_status === 'none' }"
            @click="onCityChange(city.id)"
          >
            <template #prepend>
              <span class="mr-2">{{ CITY_STATUS_DOT[city.connector_status] }}</span>
            </template>
            <v-list-item-title>{{ cityLabel(city) }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ city.country_iso2 }} · {{ t(`common.city.status.${city.connector_status}`) }}
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-menu>

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
            <template #prepend>
              <span class="mr-2">{{ opt.flag }}</span>
            </template>
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

<style scoped>
/* One single, non-wrapping row: [logo] [ | city  status ]. Every block shares
   the same height (--header-block-height, = the logo's height) and is
   centered on it, so nudging one block (padding/margin) never moves the others. */
.app-header-brand {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  height: var(--header-block-height);
  white-space: nowrap;
}

.app-header-logo,
.app-header-context {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: nowrap;
  align-items: center;
  height: var(--header-block-height);
}

.app-header-context {
  gap: 8px;
  margin-left: 12px;
}

.app-header-sep,
.app-header-city,
.app-header-status {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  height: 100%;
  line-height: 1;
}
</style>
