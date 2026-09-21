<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import FactorContribution from '@/components/charts/FactorContribution.vue'
import SignalsTimeline from '@/components/charts/SignalsTimeline.vue'
import WidgetCard from '@/components/common/WidgetCard.vue'
import ResilienceMap from '@/components/map/ResilienceMap.vue'

const { t } = useI18n()

const kpis = [
  { key: 'resilienceScore', icon: 'mdi-shield-check-outline' },
  { key: 'environmentalRisk', icon: 'mdi-waves' },
  { key: 'activeWarnings', icon: 'mdi-alert-outline' },
  { key: 'monitoredZones', icon: 'mdi-map-marker-radius-outline' },
  { key: 'dataSources', icon: 'mdi-database-outline' },
  { key: 'aiMonitoring', icon: 'mdi-creation-outline' },
]
</script>

<template>
  <div>
    <v-alert
      type="info"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      {{ t('dashboard.placeholderNotice') }}
    </v-alert>

    <v-row
      dense
      class="mb-2"
    >
      <v-col
        v-for="kpi in kpis"
        :key="kpi.key"
        cols="6"
        sm="4"
        md="2"
      >
        <v-card
          variant="flat"
          border
          class="pa-3 h-100"
        >
          <div class="d-flex align-center justify-space-between mb-1">
            <v-icon
              :icon="kpi.icon"
              color="primary"
              size="20"
            />
          </div>
          <div class="text-caption text-medium-emphasis aq-truncate">
            {{ t(`dashboard.kpi.${kpi.key}`) }}
          </div>
          <div class="text-h6 font-weight-bold">
            —
          </div>
        </v-card>
      </v-col>
    </v-row>

    <v-row dense>
      <v-col
        cols="12"
        lg="8"
      >
        <ResilienceMap
          widget-id="dashboard-map"
          :hero-height="440"
        />
      </v-col>
      <v-col
        cols="12"
        lg="4"
      >
        <WidgetCard
          widget-id="situation-brief"
          :title="t('dashboard.situationBrief.title')"
          :empty="true"
          :empty-text="t('dashboard.situationBrief.notAvailable')"
          :min-height="440"
        />
      </v-col>
    </v-row>

    <v-row
      dense
      class="mt-2"
    >
      <v-col
        cols="12"
        md="8"
      >
        <SignalsTimeline
          widget-id="signals-timeline"
          :title="t('dashboard.timeline.title')"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="12"
        md="4"
      >
        <WidgetCard
          widget-id="current-warning"
          :title="t('dashboard.currentWarning.title')"
          :empty="true"
          :empty-text="t('dashboard.currentWarning.none')"
          :min-height="340"
        />
      </v-col>
    </v-row>

    <v-row
      dense
      class="mt-2"
    >
      <v-col
        cols="12"
        md="6"
      >
        <FactorContribution
          widget-id="factor-contribution"
          :title="t('dashboard.factorContribution.title')"
          :empty-text="t('common.status.empty')"
        />
      </v-col>
      <v-col
        cols="12"
        md="6"
      >
        <WidgetCard
          widget-id="source-health"
          :title="t('dashboard.sourceHealth.title')"
          :empty="true"
          :empty-text="t('sources.empty')"
          :min-height="300"
        />
      </v-col>
    </v-row>
  </div>
</template>
