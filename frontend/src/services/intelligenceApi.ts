import { api } from '@/services/api'
import type { AIIntelligenceStatus, SituationBrief, TriggerAnalysisResult } from '@/types'

// Session 022 (user request): the Situation Brief now follows the viewer's
// selected city instead of always being about Toulouse — `cityId` degrades
// gracefully server-side (omitted/unrecognized both fall back to the
// primary city, same default as before this param existed), same pattern
// as every other city-scoped endpoint in this app.
export function fetchLatestBrief(cityId?: string | null) {
  return api.get<SituationBrief | null>('/intelligence/brief', { params: cityId ? { city_id: cityId } : {} }).then((r) => r.data)
}

export function fetchIntelligenceStatus() {
  return api.get<AIIntelligenceStatus>('/intelligence/status').then((r) => r.data)
}

// `language` defaults server-side to the deployment's default locale when
// omitted — pass the viewer's own active UI language for a manual refresh
// (Master Spec §19: "active UI language passed to the AI"). `cityId` same
// city-following behavior as fetchLatestBrief above.
export function triggerAnalysis(language?: string, cityId?: string | null) {
  return api.post<TriggerAnalysisResult>('/intelligence/analyze', { language, city_id: cityId ?? undefined }).then((r) => r.data)
}
