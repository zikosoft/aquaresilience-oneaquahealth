import { api } from '@/services/api'
import type { EarlyWarning, RiskScore, RiskTrajectory } from '@/types'

// Session 018: cityId is optional so every existing caller (and every
// existing test) keeps working unchanged — see app/services/city_context.py.
export function fetchCurrentRisk(cityId?: string | null) {
  return api.get<RiskScore>('/risk/current', { params: cityId ? { city_id: cityId } : {} }).then((r) => r.data)
}

// Session 018 — WOW #4: Predictive Risk Trajectory.
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
