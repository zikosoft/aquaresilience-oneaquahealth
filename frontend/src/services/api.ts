import axios, { AxiosError } from 'axios'

import router from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import type { ApiErrorEnvelope } from '@/types'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 15000,
})

api.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.accessToken) {
    config.headers.Authorization = `Bearer ${authStore.accessToken}`
  }
  return config
})

let refreshInFlight: Promise<string | null> | null = null

api.interceptors.response.use(
  (response) => {
    // A successful non-GET request proves the platform is no longer (or
    // never was) blocking writes — clears a banner shown from an earlier
    // MAINTENANCE_MODE response without needing a separate poll.
    const method = response.config.method?.toUpperCase()
    if (method && method !== 'GET') {
      useUiStore().setMaintenanceModeActive(false)
    }
    return response
  },
  async (error: AxiosError<ApiErrorEnvelope>) => {
    const originalRequest = error.config as (typeof error.config & { _retry?: boolean }) | undefined
    const status = error.response?.status
    const authStore = useAuthStore()

    // Session 017: Settings > System > Maintenance mode is now a real,
    // cross-cutting write-blocking gate (see backend
    // app/core/maintenance.py) — surface it as one consistent app-wide
    // banner (DefaultLayout.vue) instead of every mutating call site having
    // to special-case this error individually.
    const uiStore = useUiStore()
    if (status === 503 && error.response?.data?.error?.code === 'MAINTENANCE_MODE') {
      uiStore.setMaintenanceModeActive(true)
    }

    if (status === 401 && originalRequest && !originalRequest._retry && authStore.refreshToken) {
      originalRequest._retry = true
      refreshInFlight ??= authStore.refreshAccessToken()
      const newToken = await refreshInFlight
      refreshInFlight = null

      if (newToken) {
        originalRequest.headers = originalRequest.headers ?? {}
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return api(originalRequest)
      }

      authStore.clearSession()
      router.push({ name: 'login', query: { sessionExpired: '1' } })
    }

    return Promise.reject(error)
  },
)

export function extractApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError<ApiErrorEnvelope>(error) && error.response?.data?.error?.message) {
    return error.response.data.error.message
  }
  return fallback
}

export function apiErrorCode(error: unknown): string | undefined {
  if (axios.isAxiosError<ApiErrorEnvelope>(error)) {
    return error.response?.data?.error?.code
  }
  return undefined
}
