<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'

import ChartShell from '@/components/charts/ChartShell.vue'
import { useUiStore } from '@/stores/ui'

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

const uiStore = useUiStore()

const option = computed<EChartsOption | null>(() => {
  if (!props.values || props.values.length === 0) return null
  const categories = props.labels ?? props.values.map((_, i) => String(i))
  // P4.1: real (if compact) X/Y axes so a duration change (24h/48h/72h...)
  // is visibly reflected, not just present in the underlying data. Only a
  // handful of x-axis ticks are shown (interval computed from the series
  // length) to keep the sparkline readable at its small card size.
  const maxTicks = 4
  const tickInterval = Math.max(0, Math.ceil(categories.length / maxTicks) - 1)
  // Session 017: these were hardcoded black-based colors, which vanish
  // against a dark background — ChartShell already passes VChart a
  // 'dark'/light ECharts theme (see its :theme prop), but an *explicit*
  // axisLabel/axisLine/splitLine color always overrides the theme's own,
  // so the axes silently went near-invisible in dark mode (user report:
  // "les 8 graphs ne sont pas clairs, il faut les axes"). Deriving from
  // uiStore.isDark instead — rather than dropping color entirely like
  // SignalsTimeline.vue does — keeps these intentionally subtler than the
  // theme default at this small card size, in both themes.
  const axisLineColor = uiStore.isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.12)'
  const splitLineColor = uiStore.isDark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.06)'
  const axisLabelColor = uiStore.isDark ? 'rgba(255,255,255,0.65)' : 'rgba(0,0,0,0.5)'
  return {
    grid: { left: 36, right: 8, top: 10, bottom: 20 },
    xAxis: {
      type: 'category',
      show: true,
      data: categories,
      boundaryGap: false,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: axisLineColor } },
      axisLabel: { show: true, fontSize: 9, interval: tickInterval, color: axisLabelColor },
    },
    yAxis: {
      type: 'value',
      show: true,
      splitNumber: 2,
      splitLine: { lineStyle: { color: splitLineColor } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: true, fontSize: 9, color: axisLabelColor },
    },
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
    :min-height="180"
    :allow-fullscreen="false"
  />
</template>
