<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'

import ChartShell from '@/components/charts/ChartShell.vue'

const props = withDefaults(
  defineProps<{
    widgetId: string
    title: string
    values?: number[] | null
    labels?: string[] | null
    color?: string
    loading?: boolean
    error?: string | null
    emptyText?: string
  }>(),
  {
    values: null,
    labels: null,
    color: '#0B5FA5',
    loading: false,
    error: null,
    emptyText: '',
  },
)

const option = computed<EChartsOption | null>(() => {
  if (!props.values || props.values.length === 0) return null
  return {
    grid: { left: 4, right: 4, top: 8, bottom: 4 },
    xAxis: { type: 'category', show: false, data: props.labels ?? props.values.map((_, i) => String(i)) },
    yAxis: { type: 'value', show: false },
    tooltip: { trigger: 'axis' },
    series: [
      {
        type: 'line',
        data: props.values,
        smooth: true,
        symbol: 'none',
        areaStyle: { opacity: 0.15 },
        lineStyle: { width: 2, color: props.color },
        itemStyle: { color: props.color },
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
    :min-height="160"
    :allow-fullscreen="false"
  />
</template>
