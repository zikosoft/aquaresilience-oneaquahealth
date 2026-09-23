<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'

export interface TimelineSeries {
  name: string
  color?: string
  values: number[]
  // Set to 1 to plot this series against a secondary (right-hand) value
  // axis — used when two series share a chart but have very different
  // units/scales (e.g. water level in mm vs. precipitation in mm but two
  // orders of magnitude apart), so one doesn't flatten the other to a
  // straight line near zero.
  yAxisIndex?: 0 | 1
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
  const usesSecondAxis = props.series.some((s) => s.yAxisIndex === 1)
  return {
    grid: { left: 48, right: usesSecondAxis ? 48 : 16, top: 32, bottom: 32 },
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    xAxis: { type: 'category', data: props.timestamps, boundaryGap: false },
    yAxis: usesSecondAxis ? [{ type: 'value' }, { type: 'value' }] : { type: 'value' },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 0 }],
    series: props.series.map((s) => ({
      name: s.name,
      type: 'line',
      smooth: true,
      symbol: 'none',
      data: s.values,
      yAxisIndex: s.yAxisIndex ?? 0,
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
