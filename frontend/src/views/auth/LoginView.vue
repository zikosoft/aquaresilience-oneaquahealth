<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import BrandLogo from '@/components/branding/BrandLogo.vue'
import { apiErrorCode, extractApiErrorMessage } from '@/services/api'
import { trackEvent } from '@/services/analytics'
import { useAuthStore } from '@/stores/auth'
import { SUPPORTED_LOCALES, setLocale, type AppLocale } from '@/i18n'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const errorMessage = ref<string | null>(null)

const sessionExpired = route.query.sessionExpired === '1'

async function onSubmit(): Promise<void> {
  errorMessage.value = null
  loading.value = true
  try {
    await authStore.login(email.value, password.value)
    trackEvent('login_success')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    router.push(redirect)
  } catch (err) {
    const code = apiErrorCode(err)
    trackEvent('login_failed', { reason: code ?? 'unknown' })
    if (code === 'RATE_LIMITED') {
      errorMessage.value = t('auth.login.rateLimited')
    } else if (code === 'UNAUTHORIZED') {
      errorMessage.value = t('auth.login.invalidCredentials')
    } else {
      errorMessage.value = extractApiErrorMessage(err, t('auth.login.genericError'))
    }
  } finally {
    loading.value = false
  }
}

function onLocaleChange(code: AppLocale): void {
  setLocale(code)
}
</script>

<template>
  <v-app>
    <v-main
      class="d-flex align-center justify-center"
      style="min-height: 100vh"
    >
      <v-container class="d-flex flex-column align-center">
        <v-card
          width="420"
          max-width="94vw"
          class="pa-2"
          elevation="4"
        >
          <v-card-item>
            <div class="d-flex justify-center mb-2">
              <BrandLogo :height="125" />
            </div>
            <div class="d-flex align-center justify-space-between">
              <v-card-subtitle class="text-wrap pa-0">
                {{ t('auth.login.subtitle') }}
              </v-card-subtitle>
              <v-menu>
                <template #activator="{ props: menuProps }">
                  <v-btn
                    v-bind="menuProps"
                    variant="text"
                    size="small"
                    class="text-none"
                    prepend-icon="mdi-web"
                  >
                    {{ SUPPORTED_LOCALES.find((l) => l.code === locale)?.label }}
                  </v-btn>
                </template>
                <v-list>
                  <v-list-item
                    v-for="opt in SUPPORTED_LOCALES"
                    :key="opt.code"
                    :active="locale === opt.code"
                    @click="onLocaleChange(opt.code)"
                  >
                    <v-list-item-title>{{ opt.label }}</v-list-item-title>
                  </v-list-item>
                </v-list>
              </v-menu>
            </div>
          </v-card-item>

          <v-card-text>
            <v-alert
              v-if="sessionExpired"
              type="info"
              variant="tonal"
              class="mb-4"
              density="compact"
            >
              {{ t('auth.session.expired') }}
            </v-alert>
            <v-alert
              v-if="errorMessage"
              type="error"
              variant="tonal"
              class="mb-4"
              density="compact"
            >
              {{ errorMessage }}
            </v-alert>

            <v-form @submit.prevent="onSubmit">
              <v-text-field
                v-model="email"
                :label="t('auth.login.email')"
                type="email"
                autocomplete="username"
                prepend-inner-icon="mdi-email-outline"
                required
                class="mb-2"
              />
              <v-text-field
                v-model="password"
                :label="t('auth.login.password')"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                prepend-inner-icon="mdi-lock-outline"
                :append-inner-icon="showPassword ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
                required
                class="mb-2"
                @click:append-inner="showPassword = !showPassword"
              />
              <v-btn
                type="submit"
                color="primary"
                block
                size="large"
                :loading="loading"
                class="mt-2"
              >
                {{ t('auth.login.submit') }}
              </v-btn>
            </v-form>
          </v-card-text>
        </v-card>
      </v-container>
    </v-main>
  </v-app>
</template>
