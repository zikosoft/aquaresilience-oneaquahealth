<script setup lang="ts">
// Session 022 (user request): centralizes the brand logo used on both the
// Login page and the app header, so a future rebrand only needs to change
// this one component instead of two independent copies.
//
// Session 023 (user request): the team's real logo is in place now
// (assets/brand/logo.png), replacing the earlier Material Design icon +
// separate "AquaResilience" text placeholder. The logo image already bakes
// in the wordmark, so there's no separate text node here anymore — the
// common.appName i18n key is still used, just as the image's alt text for
// accessibility/screen readers.
//
// To swap the logo again later: replace src/assets/brand/logo.png with the
// new image (any aspect ratio works — height is fixed below, width follows
// automatically) and nothing else in the app needs to change.
import { useI18n } from 'vue-i18n'
import logoUrl from '@/assets/brand/logo.png'

withDefaults(
  defineProps<{
    /** Logo height in px; width follows the image's own aspect ratio. */
    height?: number
  }>(),
  { height: 32 },
)

const { t } = useI18n()
</script>

<template>
  <img
    :src="logoUrl"
    :alt="t('common.appName')"
    :style="{ height: `${height}px`, width: 'auto' }"
  >
</template>
