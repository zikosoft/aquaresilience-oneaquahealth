<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed, nextTick, ref, watch } from 'vue'
import VChart from 'vue-echarts'

import WidgetCard from '@/components/common/WidgetCard.vue'
import { useUiStore } from '@/stores/ui'

const props = withDefaults(
  defineProps<{
    widgetId: string
    title: string
    option: EChartsOption | null
    loading?: boolean
    error?: string | null
    emptyText?: string
    minHeight?: string | number
  }>(),
  {
    loading: false,
    error: null,
    emptyText: '',
    minHeight: 320,
  },
)

const uiStore = useUiStore()

const isEmpty = computed(() => !props.loading && !props.error && props.option === null)

// vue-echarts renders its canvas inside an internal `.echarts-host` div that
// it creates itself (not part of this component's template). That div has
// no height rule of its own, so — being a plain block element — it sizes to
// its own content (auto height) rather than filling this Vuetify flex-column
// card, which only gives *this* element's outer box a real height via
// flex-grow. The result: echarts permanently measures a 0px-tall container
// and renders a 0-height canvas, no matter how often `resize()` is called
// afterwards, because the div it measures never had a height to report. The
// global rule below (in the unscoped <style> block, since scoped CSS cannot
// reach markup a third-party library injects at runtime) closes that gap by
// making `.echarts-host` fill its parent's resolved height.
const chartRef = ref<InstanceType<typeof VChart> | null>(null)

// Widget fullscreen still changes this card's actual pixel size outside of
// any prop change vue-echarts would otherwise react to, so keep one explicit
// resize for that transition (mirrors the same pattern used for the MapLibre
// widget).
watch(
  () => uiStore.widgetFullscreenId,
  async () => {
    await nextTick()
    chartRef.value?.resize()
  },
)
</script>

<template>
  <WidgetCard
    :widget-id="widgetId"
    :title="title"
    :loading="loading"
    :error="error"
    :empty="isEmpty"
    :empty-text="emptyText"
    :min-height="minHeight"
  >
    <VChart
      v-if="option"
      ref="chartRef"
      class="flex-grow-1"
      style="width: 100%; min-height: 240px"
      :option="option"
      :theme="uiStore.isDark ? 'dark' : undefined"
      autoresize
    />
  </WidgetCard>
</template>

<style>
/* Global and unscoped on purpose — see the comment above `chartRef`. A plain
   `height: 100%` on `.echarts-host` is not reliable here: it depends on
   `.echarts` being recognized as a definite-height percentage base, which a
   flex-item whose own height comes from flex-grow (rather than an explicit
   CSS height) is not guaranteed to be. Making `.echarts` itself a column
   flex container and stretching `.echarts-host` to fill it via flex-grow
   sidesteps percentage-height resolution entirely and works reliably. */
.echarts {
  display: flex !important;
  flex-direction: column;
}
.echarts-host {
  flex: 1 1 auto !important;
  min-height: 0 !important;
}
</style>
