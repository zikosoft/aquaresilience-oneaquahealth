<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import logoDefaultUrl from '@/assets/brand/logo.png'
import logoHeaderUrl from '@/assets/brand/logo-header.png'

const props = withDefaults(
  defineProps<{
    /** Logo height in px; width follows the image's own aspect ratio. */
    height?: number
    /** 'default' = logo.png (Login page). 'header' = logo-header.png (app bar). */
    variant?: 'default' | 'header'
  }>(),
  { height: 32, variant: 'default' },
)

const { t } = useI18n()

const logoUrl = props.variant === 'header' ? logoHeaderUrl : logoDefaultUrl
</script>

<template>
  <img
    :src="logoUrl"
    :alt="t('common.appName')"
    :style="{ height: `${height}px`, width: 'auto' }"
  >
</template>
