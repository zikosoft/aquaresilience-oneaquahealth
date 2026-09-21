<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'

export interface TimelineSeries {
  name: string
  color?: string
  values: number[]
}

import ChartShell from '@/components/charts/ChartShell.vue'

const props = withDefaults(
  defineProps<{
    widgetId: string
    title: string
    timestamps?: string[] | null
    series?: TimelineSeries[] | null
    loading?: boolean
    error?: string | null
    emptyText?: string
  }>(),
  {
    timestamps: null,
    series: null,
    loading: false,
    error: null,
    emptyText: '',
  },
)

const option = computed<EChartsOption | null>(() => {
  if (!props.timestamps?.length || !props.series?.length) return null
  return {
    grid: { left: 48, right: 16, top: 32, bottom: 32 },
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    xAxis: { type: 'category', data: props.timestamps, boundaryGap: false },
    yAxis: { type: 'value' },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 0 }],
    series: props.series.map((s) => ({
      name: s.name,
      type: 'line',
      smooth: true,
      symbol: 'none',
      data: s.values,
      lineStyle: s.color ? { color: s.color } : undefined,
      itemStyle: s.color ? { color: s.color } : undefined,
    })),
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
    :min-height="340"
  />
</template>
