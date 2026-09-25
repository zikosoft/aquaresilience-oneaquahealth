import { api } from '@/services/api'
import type { EnvironmentalSummary, SourceHealth, Station, StationTimeseries } from '@/types'

export function fetchSources() {
  return api.get<SourceHealth[]>('/environmental/sources').then((r) => r.data)
}

// Session 020: write-only — same pattern as the AI Provider settings'
// api_key field. The backend never echoes the key back.
export function updateSourceCredentials(sourceId: string, apiKey: string) {
  return api
    .put<SourceHealth>(`/environmental/sources/${sourceId}/credentials`, { api_key: apiKey })
    .then((r) => r.data)
}

// Session 020 (user request): optional city_id so the map can show only the
// selected city's own stations — "quand on change la ville dans le
// dashboard il faut que la map change aussi". Omitted, unchanged global
// list (same as every caller before this).
export function fetchStations(cityId?: string | null) {
  return api
    .get<Station[]>('/environmental/stations', { params: cityId ? { city_id: cityId } : {} })
    .then((r) => r.data)
}

export function fetchStationTimeseries(stationId: string, hours = 48) {
  return api
    .get<StationTimeseries>(`/environmental/stations/${stationId}/timeseries`, { params: { hours } })
    .then((r) => r.data)
}

// Session 018: cityId is optional so every existing caller (and every
// existing test) keeps working unchanged — see app/services/city_context.py.
export function fetchEnvironmentalSummary(hours = 48, cityId?: string | null) {
  return api
    .get<EnvironmentalSummary>('/environmental/summary', { params: cityId ? { hours, city_id: cityId } : { hours } })
    .then((r) => r.data)
}
