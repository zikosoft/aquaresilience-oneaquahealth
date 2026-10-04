import { api } from '@/services/api'
import type { EarlyWarning, RiskScore, RiskTrajectory } from '@/types'

export function fetchCurrentRisk(cityId?: string | null) {
  return api.get<RiskScore>('/risk/current', { params: cityId ? { city_id: cityId } : {} }).then((r) => r.data)
}

export function fetchRiskTrajectory(cityId?: string | null) {
  return api.get<RiskTrajectory>('/risk/trajectory', { params: cityId ? { city_id: cityId } : {} }).then((r) => r.data)
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
