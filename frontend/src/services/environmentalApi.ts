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

export function fetchEnvironmentalSummary(hours = 48) {
  return api.get<EnvironmentalSummary>('/environmental/summary', { params: { hours } }).then((r) => r.data)
}
