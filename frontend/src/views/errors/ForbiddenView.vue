<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const router = useRouter()
</script>

<template>
  <v-container
    class="d-flex flex-column align-center justify-center text-center"
    style="min-height: 60vh"
  >
    <v-icon
      icon="mdi-shield-lock-outline"
      size="64"
      color="warning"
      class="mb-4"
    />
    <h1 class="text-h5 mb-2">
      403
    </h1>
    <p class="text-body-1 text-medium-emphasis mb-4">
      {{ t('common.status.error') }}
    </p>
    <v-btn
      color="primary"
      @click="router.push({ name: 'dashboard' })"
    >
      {{ t('common.actions.back') }}
    </v-btn>
  </v-container>
</template>
