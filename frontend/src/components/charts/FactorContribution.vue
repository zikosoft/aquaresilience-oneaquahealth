<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'

export interface FactorContributionItem {
  factor: string
  contribution: number
}

import ChartShell from '@/components/charts/ChartShell.vue'

const props = withDefaults(
  defineProps<{
    widgetId: string
    title: string
    items?: FactorContributionItem[] | null
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

const option = computed<EChartsOption | null>(() => {
  if (!props.items?.length) return null
  return {
    grid: { left: 120, right: 24, top: 16, bottom: 16 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', max: 100 },
    yAxis: { type: 'category', data: props.items.map((i) => i.factor) },
    series: [
      {
        type: 'bar',
        data: props.items.map((i) => i.contribution),
        itemStyle: { color: '#106E7C', borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', formatter: '{c}%' },
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
