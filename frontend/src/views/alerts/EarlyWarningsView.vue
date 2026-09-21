<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const lifecycleSteps = ['active', 'acknowledged', 'resolved'] as const
</script>

<template>
  <div>
    <v-card
      variant="flat"
      border
      class="mb-4 pa-4"
    >
      <div class="d-flex flex-wrap ga-2 align-center">
        <span class="text-body-2 text-medium-emphasis mr-2">{{ t('alerts.title') }}:</span>
        <template
          v-for="(step, idx) in lifecycleSteps"
          :key="step"
        >
          <v-chip
            size="small"
            variant="outlined"
          >
            {{ t(`alerts.lifecycle.${step}`) }}
          </v-chip>
          <v-icon
            v-if="idx < lifecycleSteps.length - 1"
            icon="mdi-arrow-right"
            size="16"
            class="text-medium-emphasis"
          />
        </template>
      </div>
    </v-card>

    <v-card
      variant="flat"
      border
      class="pa-8 d-flex flex-column align-center justify-center text-center"
    >
      <v-icon
        icon="mdi-bell-check-outline"
        size="48"
        color="medium-emphasis"
        class="mb-3"
      />
      <p class="text-body-1 text-medium-emphasis">
        {{ t('alerts.empty') }}
      </p>
    </v-card>
  </div>
</template>
