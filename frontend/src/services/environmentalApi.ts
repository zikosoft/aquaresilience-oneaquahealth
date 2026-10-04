import { api } from '@/services/api'
import type { EnvironmentalSummary, SourceHealth, Station, StationTimeseries } from '@/types'

export function fetchSources() {
  return api.get<SourceHealth[]>('/environmental/sources').then((r) => r.data)
}

export function updateSourceCredentials(sourceId: string, apiKey: string) {
  return api
    .put<SourceHealth>(`/environmental/sources/${sourceId}/credentials`, { api_key: apiKey })
    .then((r) => r.data)
}

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

export function fetchEnvironmentalSummary(hours = 48, cityId?: string | null) {
  return api
    .get<EnvironmentalSummary>('/environmental/summary', { params: cityId ? { hours, city_id: cityId } : { hours } })
    .then((r) => r.data)
}
