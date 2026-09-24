import { api } from '@/services/api'
import type { EnvironmentalSummary, SourceHealth, Station, StationTimeseries } from '@/types'

export function fetchSources() {
  return api.get<SourceHealth[]>('/environmental/sources').then((r) => r.data)
}

export function fetchStations() {
  return api.get<Station[]>('/environmental/stations').then((r) => r.data)
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
