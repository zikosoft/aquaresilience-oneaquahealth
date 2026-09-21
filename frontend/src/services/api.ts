import axios, { AxiosError } from 'axios'

import router from '@/router'
import { useAuthStore } from '@/stores/auth'
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
  (response) => response,
  async (error: AxiosError<ApiErrorEnvelope>) => {
    const originalRequest = error.config as (typeof error.config & { _retry?: boolean }) | undefined
    const status = error.response?.status
    const authStore = useAuthStore()

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
