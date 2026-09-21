<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const headers = [
  { title: t('sources.table.name'), key: 'name' },
  { title: t('sources.table.category'), key: 'category' },
  { title: t('sources.table.status'), key: 'status' },
  { title: t('sources.table.lastSync'), key: 'lastSync' },
]
</script>

<template>
  <v-card
    variant="flat"
    border
  >
    <v-data-table
      :headers="headers"
      :items="[]"
      :no-data-text="t('sources.empty')"
      density="comfortable"
    />
  </v-card>
</template>
