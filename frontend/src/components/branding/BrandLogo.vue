<script setup lang="ts">
// Session 022 (user request): centralizes the "logo + product name" visual
// treatment that used to be duplicated independently in AppHeader.vue and
// LoginView.vue. Today the "logo" is just a Material Design icon (there is
// no real logo image anywhere in the project yet — see favicon.svg for the
// only brand asset that exists), and the name comes from the common.appName
// i18n key (identical across all 9 locales). The point of this component is
// NOT to rebrand anything now — it's to leave exactly one place to edit
// later when the team has its own logo: swap the <v-icon> below for an
// <img :src="..."> (or a <slot>), and/or point common.appName at a new
// constant, and every page that uses <BrandLogo /> picks it up automatically.
import { useI18n } from 'vue-i18n'

withDefaults(
  defineProps<{
    /** Icon size in px (Vuetify v-icon `size`). */
    size?: number
    /** Classes applied to the product-name text span. */
    textClass?: string
  }>(),
  {
    size: 28,
    textClass: 'font-weight-bold',
  },
)

const { t } = useI18n()
</script>

<template>
  <div class="d-flex align-center ga-2">
    <v-icon
      icon="mdi-water-outline"
      color="primary"
      :size="size"
    />
    <span :class="textClass">{{ t('common.appName') }}</span>
  </div>
</template>
