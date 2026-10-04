<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import ChartShell from '@/components/charts/ChartShell.vue'

export interface ResilienceRadarItem {
  factor: string
  // 0..100 — the factor's OWN normalized severity (RiskFactor.normalized_value
  // * 100), not its weighted contribution to the combined score (that's
  // what the neighboring FactorContribution bar chart already shows). This
  // is what makes the radar a distinct, complementary view rather than the
  // same numbers redrawn in a different shape.
  value: number
  available: boolean
}

const props = withDefaults(
  defineProps<{
    widgetId: string
    title: string
    items?: ResilienceRadarItem[] | null
    loading?: boolean
    error?: string | null
    emptyText?: string
  }>(),
  {
    items: null,
    loading: false,
    error: null,
    emptyText: '',
  },
)

const { t } = useI18n()

const option = computed<EChartsOption | null>(() => {
  const items = props.items
  if (!items?.length) return null

  return {
    tooltip: {
      trigger: 'item',
      formatter: () =>
        items
          .map((i) =>
            i.available
              ? `${i.factor}: ${i.value}/100`
              : `${i.factor}: ${t('dashboard.resilienceRadar.notAvailable')}`,
          )
          .join('<br/>'),
    },
    radar: {
      indicator: items.map((i) => ({ name: i.factor, max: 100 })),
      radius: '65%',
      splitNumber: 4,
      axisName: { fontSize: 11 },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: items.map((i) => (i.available ? i.value : 0)),
            name: props.title,
            areaStyle: { color: '#106E7C', opacity: 0.25 },
            lineStyle: { color: '#106E7C', width: 2 },
            itemStyle: { color: '#106E7C' },
          },
        ],
      },
    ],
  }
})
</script>

<template>
  <ChartShell
    :widget-id="widgetId"
    :title="title"
    :option="option"
    :loading="loading"
    :error="error"
    :empty-text="emptyText"
    :min-height="300"
  />
</template>
