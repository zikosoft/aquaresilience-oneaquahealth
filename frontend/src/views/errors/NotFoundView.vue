<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const router = useRouter()
</script>

<template>
  <v-app>
    <v-main>
      <v-container
        class="d-flex flex-column align-center justify-center text-center"
        style="min-height: 100vh"
      >
        <v-icon
          icon="mdi-map-marker-question-outline"
          size="64"
          color="primary"
          class="mb-4"
        />
        <h1 class="text-h5 mb-2">
          404
        </h1>
        <p class="text-body-1 text-medium-emphasis mb-4">
          {{ t('common.status.empty') }}
        </p>
        <v-btn
          color="primary"
          @click="router.push({ name: 'dashboard' })"
        >
          {{ t('common.actions.back') }}
        </v-btn>
      </v-container>
    </v-main>
  </v-app>
</template>
