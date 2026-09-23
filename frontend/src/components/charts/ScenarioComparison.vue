<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'

import ChartShell from '@/components/charts/ChartShell.vue'

const props = withDefaults(
  defineProps<{
    widgetId: string
    title: string
    currentValue?: number | null
    projectedValue?: number | null
    currentLabel?: string
    projectedLabel?: string
    loading?: boolean
    error?: string | null
    emptyText?: string
    // P4: default 100 keeps the original risk-score (0-100) usage
    // unchanged; pass null to let ECharts auto-scale for a different unit
    // (e.g. water level in mm), or an explicit number for a fixed scale.
    yAxisMax?: number | null
  }>(),
  {
    currentValue: null,
    projectedValue: null,
    currentLabel: 'Current',
    projectedLabel: 'Projected',
    loading: false,
    error: null,
    emptyText: '',
    yAxisMax: 100,
  },
)

const option = computed<EChartsOption | null>(() => {
  if (props.currentValue === null || props.projectedValue === null) return null
  return {
    grid: { left: 40, right: 16, top: 16, bottom: 24 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: [props.currentLabel, props.projectedLabel] },
    yAxis: { type: 'value', max: props.yAxisMax ?? undefined },
    series: [
      {
        type: 'bar',
        data: [
          { value: props.currentValue, itemStyle: { color: '#0B5FA5' } },
          { value: props.projectedValue, itemStyle: { color: '#E0672B' } },
        ],
        barWidth: '45%',
        label: { show: true, position: 'top' },
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
