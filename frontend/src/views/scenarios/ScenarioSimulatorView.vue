<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ScenarioComparison from '@/components/charts/ScenarioComparison.vue'

const { t } = useI18n()

const rainfall = ref(0)
const riverLevel = ref(0)
</script>

<template>
  <v-row dense>
    <v-col
      cols="12"
      md="4"
    >
      <v-card
        variant="flat"
        border
        class="pa-4"
      >
        <v-card-title class="text-subtitle-1 font-weight-bold px-0">
          {{ t('scenarios.title') }}
        </v-card-title>
        <v-slider
          v-model="rainfall"
          :label="t('scenarios.controls.rainfall')"
          min="-50"
          max="100"
          step="5"
          thumb-label
          class="mt-6"
          disabled
        />
        <v-slider
          v-model="riverLevel"
          :label="t('scenarios.controls.riverLevel')"
          min="-50"
          max="100"
          step="5"
          thumb-label
          disabled
        />
        <v-btn
          color="primary"
          block
          disabled
          class="mt-2"
        >
          {{ t('scenarios.run') }}
        </v-btn>
        <p class="text-caption text-medium-emphasis mt-4">
          {{ t('scenarios.empty') }}
        </p>
      </v-card>
    </v-col>
    <v-col
      cols="12"
      md="8"
    >
      <ScenarioComparison
        widget-id="scenario-comparison"
        :title="`${t('scenarios.current')} → ${t('scenarios.projected')}`"
        :empty-text="t('scenarios.empty')"
      />
    </v-col>
  </v-row>
</template>
