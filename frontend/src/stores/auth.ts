import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as authApi from '@/services/authApi'
import type { Me } from '@/types'

const ACCESS_TOKEN_KEY = 'aquaresilience.access_token'
const REFRESH_TOKEN_KEY = 'aquaresilience.refresh_token'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(sessionStorage.getItem(ACCESS_TOKEN_KEY))
  const refreshToken = ref<string | null>(localStorage.getItem(REFRESH_TOKEN_KEY))
  const currentUser = ref<Me | null>(null)
  const initializing = ref(false)

  const isAuthenticated = computed(() => Boolean(accessToken.value && currentUser.value))
  const permissions = computed(() => new Set(currentUser.value?.permissions ?? []))

  function can(moduleCode: string, permissionCode: string): boolean {
    return permissions.value.has(`${moduleCode}:${permissionCode}`) || permissions.value.has(`${moduleCode}:ADMIN`)
  }

  function setTokens(tokens: { access_token: string; refresh_token: string }): void {
    accessToken.value = tokens.access_token
    refreshToken.value = tokens.refresh_token
    sessionStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
  }

  function clearSession(): void {
    accessToken.value = null
    refreshToken.value = null
    currentUser.value = null
    sessionStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  }

  async function login(email: string, password: string): Promise<void> {
    const tokens = await authApi.login(email, password)
    setTokens(tokens)
    currentUser.value = await authApi.me()
  }

  async function fetchCurrentUser(): Promise<void> {
    if (!accessToken.value) return
    currentUser.value = await authApi.me()
  }

  async function logout(): Promise<void> {
    if (refreshToken.value) {
      try {
        await authApi.logout(refreshToken.value)
      } catch {
        // Best-effort revoke; clear the local session regardless.
      }
    }
    clearSession()
  }

  async function refreshAccessToken(): Promise<string | null> {
    if (!refreshToken.value) return null
    try {
      const tokens = await authApi.refresh(refreshToken.value)
      setTokens(tokens)
      return tokens.access_token
    } catch {
      return null
    }
  }

  async function initialize(): Promise<void> {
    if (!accessToken.value) return
    initializing.value = true
    try {
      await fetchCurrentUser()
    } catch {
      clearSession()
    } finally {
      initializing.value = false
    }
  }

  return {
    accessToken,
    refreshToken,
    currentUser,
    initializing,
    isAuthenticated,
    permissions,
    can,
    login,
    logout,
    clearSession,
    refreshAccessToken,
    initialize,
    fetchCurrentUser,
  }
})
