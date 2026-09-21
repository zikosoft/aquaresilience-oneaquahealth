<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import AIProviderSettings from '@/components/settings/AIProviderSettings.vue'
import GenericSettingCard from '@/components/settings/GenericSettingCard.vue'
import UsersAccessSettings from '@/components/settings/UsersAccessSettings.vue'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const route = useRoute()
const authStore = useAuthStore()

const initialTab = typeof route.query.tab === 'string' ? route.query.tab : 'general'
const tab = ref(initialTab)

const canAdminister = authStore.can('ADMINISTRATION', 'VIEW')
</script>

<template>
  <div>
    <h1 class="text-h5 font-weight-bold mb-4">
      {{ t('settings.title') }}
    </h1>

    <v-tabs
      v-model="tab"
      density="comfortable"
      class="mb-4"
      show-arrows
    >
      <v-tab value="general">
        {{ t('settings.tabs.general') }}
      </v-tab>
      <v-tab value="languages">
        {{ t('settings.tabs.languages') }}
      </v-tab>
      <v-tab value="data-sources">
        {{ t('settings.tabs.dataSources') }}
      </v-tab>
      <v-tab value="ai-provider">
        {{ t('settings.tabs.aiProvider') }}
      </v-tab>
      <v-tab value="scheduler">
        {{ t('settings.tabs.scheduler') }}
      </v-tab>
      <v-tab value="risk-engine">
        {{ t('settings.tabs.riskEngine') }}
      </v-tab>
      <v-tab value="alerts">
        {{ t('settings.tabs.alerts') }}
      </v-tab>
      <v-tab
        v-if="canAdminister"
        value="users-access"
      >
        {{ t('settings.tabs.usersAccess') }}
      </v-tab>
      <v-tab value="system">
        {{ t('settings.tabs.system') }}
      </v-tab>
    </v-tabs>

    <v-window v-model="tab">
      <v-window-item value="general">
        <GenericSettingCard
          category="general"
          setting-key="general"
          :title="t('settings.tabs.general')"
          :fields="[
            { path: 'city', label: t('settings.general.city'), type: 'text' },
            { path: 'timezone', label: t('settings.general.timezone'), type: 'text' },
            { path: 'date_format', label: t('settings.general.dateFormat'), type: 'text' },
          ]"
        />
      </v-window-item>

      <v-window-item value="languages">
        <GenericSettingCard
          category="languages"
          setting-key="languages"
          :title="t('settings.tabs.languages')"
          :fields="[
            {
              path: 'default_locale',
              label: t('settings.languages.defaultLocale'),
              type: 'select',
              options: [
                { value: 'en', label: 'English' },
                { value: 'fr', label: 'Français' },
                { value: 'es', label: 'Español' },
              ],
            },
            { path: 'enabled_locales', label: t('settings.languages.enabledLocales'), type: 'chips' },
          ]"
        />
      </v-window-item>

      <v-window-item value="data-sources">
        <v-card
          variant="flat"
          border
          class="pa-8 d-flex flex-column align-center justify-center text-center"
        >
          <v-icon
            icon="mdi-database-outline"
            size="40"
            color="medium-emphasis"
            class="mb-3"
          />
          <p class="text-body-1 text-medium-emphasis">
            {{ t('sources.empty') }}
          </p>
        </v-card>
      </v-window-item>

      <v-window-item value="ai-provider">
        <AIProviderSettings />
      </v-window-item>

      <v-window-item value="scheduler">
        <GenericSettingCard
          category="scheduler"
          setting-key="scheduler"
          :title="t('settings.tabs.scheduler')"
          :fields="[
            {
              path: 'situation_brief_interval_hours',
              label: t('settings.aiProvider.scheduledInterval'),
              type: 'number',
              suffix: 'h',
            },
          ]"
        />
      </v-window-item>

      <v-window-item value="risk-engine">
        <GenericSettingCard
          category="risk_engine"
          setting-key="risk_engine"
          :title="t('settings.tabs.riskEngine')"
          description="Deterministic risk engine weights and severity thresholds (Risk Engine implemented in P2)."
          :fields="[
            { path: 'weights.rainfall', label: 'Rainfall weight', type: 'number' },
            { path: 'weights.hydrology', label: 'Hydrology weight', type: 'number' },
            { path: 'weights.environmental', label: 'Environmental weight', type: 'number' },
            { path: 'weights.trend', label: 'Trend weight', type: 'number' },
            { path: 'thresholds.low', label: 'LOW → MODERATE threshold', type: 'number' },
            { path: 'thresholds.moderate', label: 'MODERATE → HIGH threshold', type: 'number' },
            { path: 'thresholds.high', label: 'HIGH → CRITICAL threshold', type: 'number' },
          ]"
        />
      </v-window-item>

      <v-window-item value="alerts">
        <GenericSettingCard
          category="alerts"
          setting-key="alerts"
          :title="t('settings.tabs.alerts')"
          description="Early Warning lifecycle (Alerts implemented in P2)."
          :fields="[{ path: 'lifecycle', label: t('alerts.title'), type: 'chips' }]"
        />
      </v-window-item>

      <v-window-item
        v-if="canAdminister"
        value="users-access"
      >
        <UsersAccessSettings />
      </v-window-item>

      <v-window-item value="system">
        <GenericSettingCard
          category="system"
          setting-key="system"
          :title="t('settings.tabs.system')"
          :fields="[{ path: 'maintenance_mode', label: t('settings.system.maintenanceMode'), type: 'boolean' }]"
        />
      </v-window-item>
    </v-window>
  </div>
</template>
