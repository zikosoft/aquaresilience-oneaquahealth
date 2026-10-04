<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import ChartShell from '@/components/charts/ChartShell.vue'
import type { RiskSeverity, RiskTrajectory } from '@/types'

const props = withDefaults(
  defineProps<{
    widgetId: string
    title: string
    trajectory: RiskTrajectory | null
    loading?: boolean
    error?: string | null
    emptyText?: string
  }>(),
  {
    trajectory: null,
    loading: false,
    error: null,
    emptyText: '',
  },
)

const { t } = useI18n()

const SEVERITY_HEX: Record<RiskSeverity, string> = {
  LOW: '#2E9E5B',
  MODERATE: '#E0A31D',
  HIGH: '#E0672B',
  CRITICAL: '#D64550',
}

interface PlotPoint {
  label: string
  score: number
  severity: RiskSeverity
  waterLevelMm: number | null
}

const plotPoints = computed<PlotPoint[] | null>(() => {
  const traj = props.trajectory
  if (!traj || traj.points.length === 0) return null
  return [
    {
      label: t('dashboard.trajectory.now'),
      score: traj.current_score,
      severity: traj.current_severity,
      waterLevelMm: null,
    },
    ...traj.points.map((p) => ({
      label: t('dashboard.trajectory.horizon', { hours: p.hours_ahead }),
      score: p.score,
      severity: p.severity,
      waterLevelMm: p.projected_water_level_mm,
    })),
  ]
})

const option = computed<EChartsOption | null>(() => {
  const points = plotPoints.value
  if (!points) return null

  return {
    grid: { left: 40, right: 16, top: 16, bottom: 32 },
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const first = Array.isArray(params) ? params[0] : params
        const dataIndex = (first as { dataIndex: number }).dataIndex
        const point = points[dataIndex]
        const lines = [
          `<strong>${point.label}</strong>`,
          `${t('dashboard.trajectory.score')}: ${Math.round(point.score)}/100 — ${t(`alerts.severity.${point.severity.toLowerCase()}`)}`,
        ]
        if (point.waterLevelMm !== null) {
          lines.push(`${t('dashboard.trajectory.projectedLevel')}: ${point.waterLevelMm} mm`)
        }
        return lines.join('<br/>')
      },
    },
    xAxis: { type: 'category', data: points.map((p) => p.label) },
    yAxis: { type: 'value', min: 0, max: 100 },
    series: [
      {
        type: 'line',
        data: points.map((p) => ({
          value: Math.round(p.score * 10) / 10,
          itemStyle: { color: SEVERITY_HEX[p.severity] },
        })),
        smooth: true,
        symbol: 'circle',
        symbolSize: 9,
        lineStyle: { color: '#E0672B', width: 3 },
        areaStyle: { color: '#E0672B', opacity: 0.1 },
      },
    ],
  }
})

const basisCaption = computed<string | null>(() => {
  const traj = props.trajectory
  if (!traj) return null
  if (traj.basis === 'rising_trend' && traj.trend_rate_mm_per_hour !== null) {
    return t('dashboard.trajectory.basisRising', { rate: traj.trend_rate_mm_per_hour })
  }
  if (traj.basis === 'flat_or_falling') return t('dashboard.trajectory.basisFlat')
  return t('dashboard.trajectory.basisInsufficient')
})
</script>

<template>
  <div>
    <ChartShell
      :widget-id="widgetId"
      :title="title"
      :option="option"
      :loading="loading"
      :error="error"
      :empty-text="emptyText"
      :min-height="300"
    />
    <div
      v-if="basisCaption && !loading"
      class="text-caption text-medium-emphasis px-1 pt-1"
    >
      {{ basisCaption }}
    </div>
  </div>
</template>
