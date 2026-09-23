import { api } from '@/services/api'
import type { ScenarioSimulateRequest, ScenarioSimulateResponse } from '@/types'

export function simulateScenario(payload: ScenarioSimulateRequest) {
  return api.post<ScenarioSimulateResponse>('/scenario/simulate', payload).then((r) => r.data)
}
