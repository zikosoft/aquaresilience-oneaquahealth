import { api } from '@/services/api'
import type { AIIntelligenceStatus, SituationBrief, TriggerAnalysisResult } from '@/types'

export function fetchLatestBrief() {
  return api.get<SituationBrief | null>('/intelligence/brief').then((r) => r.data)
}

export function fetchIntelligenceStatus() {
  return api.get<AIIntelligenceStatus>('/intelligence/status').then((r) => r.data)
}

// `language` defaults server-side to the deployment's default locale when
// omitted — pass the viewer's own active UI language for a manual refresh
// (Master Spec §19: "active UI language passed to the AI").
export function triggerAnalysis(language?: string) {
  return api.post<TriggerAnalysisResult>('/intelligence/analyze', { language }).then((r) => r.data)
}
