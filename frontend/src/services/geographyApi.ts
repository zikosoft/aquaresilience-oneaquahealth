import { api } from '@/services/api'
import type { City, MapTileProvider } from '@/types'

export function fetchCities() {
  return api.get<City[]>('/geography/cities').then((r) => r.data)
}

export interface MapConfig {
  tile_provider: MapTileProvider
  // P4.1: 0-100, Settings > Map-configurable opacity for the risk-level
  // circle layer rendered around the river gauge station.
  risk_layer_opacity: number
  cities: City[]
}

// P2.1: the effective map configuration (Settings > Map tab's tile
// provider + city defaults), MAP:VIEW-gated so every role that can view
// the map can fetch it — not just Settings editors. See
// `app/api/v1/geography.py`'s module docstring for why this is folded
// into one call instead of two differently-gated ones.
export function fetchMapConfig() {
  return api.get<MapConfig>('/geography/map-config').then((r) => r.data)
}
