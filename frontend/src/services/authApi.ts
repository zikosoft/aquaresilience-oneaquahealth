import { api } from '@/services/api'
import type { Me } from '@/types'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export function login(email: string, password: string) {
  return api.post<TokenPair>('/auth/login', { email, password }).then((r) => r.data)
}

export function refresh(refreshToken: string) {
  return api.post<TokenPair>('/auth/refresh', { refresh_token: refreshToken }).then((r) => r.data)
}

export function logout(refreshToken: string) {
  return api.post('/auth/logout', { refresh_token: refreshToken })
}

export function me() {
  return api.get<Me>('/auth/me').then((r) => r.data)
}
