import { api } from '@/services/api'
import type { EarlyWarning, RiskScore } from '@/types'

export function fetchCurrentRisk() {
  return api.get<RiskScore>('/risk/current').then((r) => r.data)
}

export function fetchWarnings() {
  return api.get<EarlyWarning[]>('/risk/warnings').then((r) => r.data)
}

export function acknowledgeWarning(id: string) {
  return api.post<EarlyWarning>(`/risk/warnings/${id}/acknowledge`).then((r) => r.data)
}

export function resolveWarning(id: string) {
  return api.post<EarlyWarning>(`/risk/warnings/${id}/resolve`).then((r) => r.data)
}
