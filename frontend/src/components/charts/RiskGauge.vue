<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'

import ChartShell from '@/components/charts/ChartShell.vue'

const props = withDefaults(
  defineProps<{
    widgetId: string
    title: string
    value?: number | null
    label?: string
    loading?: boolean
    error?: string | null
    emptyText?: string
  }>(),
  {
    value: null,
    label: '',
    loading: false,
    error: null,
    emptyText: '',
  },
)

const option = computed<EChartsOption | null>(() => {
  if (props.value === null || props.value === undefined) return null
  return {
    series: [
      {
        type: 'gauge',
        min: 0,
        max: 100,
        startAngle: 200,
        endAngle: -20,
        progress: { show: true, width: 14 },
        axisLine: {
          lineStyle: {
            width: 14,
            color: [
              [0.25, '#2E9E5B'],
              [0.5, '#E0A31D'],
              [0.75, '#E0672B'],
              [1, '#D64550'],
            ],
          },
        },
        pointer: { show: true },
        axisTick: { show: false },
        splitLine: { length: 10, lineStyle: { width: 2, color: '#999' } },
        axisLabel: { distance: 18, fontSize: 10 },
        detail: {
          valueAnimation: true,
          fontSize: 28,
          fontWeight: 'bold',
          offsetCenter: [0, '40%'],
          formatter: '{value}',
        },
        title: { fontSize: 12, offsetCenter: [0, '70%'] },
        data: [{ value: props.value, name: props.label }],
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
    :min-height="280"
  />
</template>
