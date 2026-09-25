export interface Role {
  id: string
  code: string
  name: string
  description: string
  is_system: boolean
}

export interface ModuleDef {
  id: string
  code: string
  name: string
  sort_order: number
}

export interface PermissionDef {
  id: string
  code: string
  name: string
}

export interface User {
  id: string
  email: string
  full_name: string
  is_active: boolean
  preferred_locale: string
  last_login_at: string | null
  created_at: string
  roles: Role[]
}

export interface Me extends User {
  permissions: string[]
}

export interface RolePermissionCell {
  role_id: string
  module_id: string
  permission_id: string
}

export interface PermissionMatrix {
  roles: Role[]
  modules: ModuleDef[]
  permissions: PermissionDef[]
  grants: RolePermissionCell[]
}

// P2.1 (D015): response to a single per-user permission-cell toggle — the
// role the user ends up on (their existing role, or a newly-cloned
// "Custom — <name>" role) plus that role's full grant set.
export interface UserPermissionsResult {
  role: Role
  grants: RolePermissionCell[]
}

export interface AppSetting {
  category: string
  key: string
  value: Record<string, unknown>
  description: string
}

// P2.1: read-only geography reference data (D016). Session 018: now 9
// OneAquaHealth consortium cities, not just Toulouse — `ResilienceMap.vue`,
// the Settings > Map tab and the header's city selector (`stores/city.ts`)
// all read this. Session 020: several more cities have real connectors now
// (Vienna/Ghent live, Oslo pending a key), so `has_live_data` alone is no
// longer "Toulouse vs. the rest" — see `connector_status` below.
export interface City {
  id: string
  label_en: string
  label_fr: string
  label_es: string
  country_iso2: string
  default_lon: number
  default_lat: number
  default_zoom: number
  has_live_data: boolean
  planned_data_source: string | null
  // Session 020: 3-tier signal for the header's city selector — 'live'
  // (real ingested data), 'pending' (a connector is registered but hasn't
  // gone live yet, e.g. Oslo awaiting its API key), or 'none' (no connector
  // has ever run for this city). Computed server-side, never inferred here.
  connector_status: 'live' | 'pending' | 'none'
}

// P4.1: 'carto_light'/'carto_dark' removed — CARTO's raster basemap tiles
// (basemaps.cartocdn.com) now require a free API key (confirmed via CARTO's
// own docs: "CARTO's free raster basemap tiles now require an API key"),
// which broke D019's "no account or API key needed for any of these"
// premise; a previously-stored setting value of either string still falls
// back to 'osm' at render time (see ResilienceMap.vue's RASTER_STYLES
// lookup), it's just no longer offered anywhere in the UI.
export type MapTileProvider = 'osm' | 'cyclosm' | 'humanitarian'

export interface MapSettings {
  tile_provider: MapTileProvider
}

export interface AIProviderConfig {
  provider: 'openai' | 'anthropic'
  model: string
  max_output_tokens: number
  scheduled_analysis_interval_minutes: number
  daily_request_ceiling: number
  event_triggered_enabled: boolean
  cooldown_seconds: number
  is_configured: boolean
  last_connection_test_ok: boolean | null
}

export interface AIProviderConfigUpdate {
  provider: 'openai' | 'anthropic'
  model: string
  api_key?: string
  max_output_tokens: number
  scheduled_analysis_interval_minutes: number
  daily_request_ceiling: number
  event_triggered_enabled: boolean
  cooldown_seconds: number
}

export interface ApiErrorEnvelope {
  error: {
    code: string
    message: string
    details?: unknown
  }
}

// --- P1: environmental data ---

export type SourceHealthStatus = 'fresh' | 'stale' | 'degraded'

// Session 020: minimal city reference for grouping the /sources page —
// mirrors app/schemas/environmental.py's SourceCityRef.
export interface SourceCityRef {
  id: string
  label_en: string
  label_fr: string
  label_es: string
}

export interface SourceHealth {
  id: string
  code: string
  name: string
  provider: string
  kind: string
  is_active: boolean
  license: string
  homepage_url: string
  health: SourceHealthStatus
  last_attempt_at: string | null
  last_success_at: string | null
  consecutive_failures: number
  last_error_message: string | null
  city: SourceCityRef | null
  requires_api_key: boolean
  is_key_configured: boolean
}

export interface LatestReading {
  variable: string
  value: number
  unit: string
  observed_at: string
}

export interface Station {
  id: string
  external_code: string
  name: string
  kind: string
  city: string
  river_name: string | null
  lon: number
  lat: number
  source_code: string
  source_health: SourceHealthStatus
  latest: LatestReading[]
}

export interface TimeseriesPoint {
  value: number
  observed_at: string
}

export interface TimeseriesSeries {
  variable: string
  unit: string
  points: TimeseriesPoint[]
}

export interface StationTimeseries {
  station_id: string
  station_name: string
  series: TimeseriesSeries[]
}

export interface EnvironmentalSummary {
  monitored_stations: number
  active_sources: number
  fresh_sources: number
  // P2.1 (D017): the trend window is caller-selectable (`?hours=`); this
  // echoes back the effective window actually used, for chart titles.
  trend_window_hours: number
  water_level: LatestReading | null
  water_level_trend: number[]
  water_level_trend_timestamps: string[]
  precipitation_24h_total_mm: number | null
  precipitation_trend: number[]
  precipitation_trend_timestamps: string[]
  temperature: LatestReading | null
  temperature_trend: number[]
  temperature_trend_timestamps: string[]
  humidity: LatestReading | null
  humidity_trend: number[]
  humidity_trend_timestamps: string[]
  // P2.1: 4 more free Open-Meteo hourly variables — same trend pattern.
  wind_speed: LatestReading | null
  wind_speed_trend: number[]
  wind_speed_trend_timestamps: string[]
  wind_direction: LatestReading | null
  wind_direction_trend: number[]
  wind_direction_trend_timestamps: string[]
  surface_pressure: LatestReading | null
  surface_pressure_trend: number[]
  surface_pressure_trend_timestamps: string[]
  uv_index: LatestReading | null
  uv_index_trend: number[]
  uv_index_trend_timestamps: string[]
  // Session 018: same convention as RiskScore — see `stores/city.ts`.
  data_available: boolean
  planned_data_source: string | null
}

// --- P2: deterministic risk engine + early warnings ---

export type RiskSeverity = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL'

export interface RiskFactor {
  key: string
  label: string
  weight: number
  normalized_value: number | null
  contribution: number
  available: boolean
}

export interface RiskScore {
  score: number
  severity: RiskSeverity
  factors: RiskFactor[]
  factors_available: number
  factors_total: number
  computed_at: string
  // Session 018: false only when a non-demo city (no live connector) was
  // requested — see `stores/city.ts` and `app/services/city_context.py`.
  data_available: boolean
  planned_data_source: string | null
}

export type EarlyWarningStatus = 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED'

export interface WarningFactorSnapshot {
  label: string
  weight: number
  normalized_value: number | null
  contribution: number
  available: boolean
}

export interface EarlyWarning {
  id: string
  severity: RiskSeverity
  status: EarlyWarningStatus
  risk_score: number
  factors: Record<string, WarningFactorSnapshot>
  message: string
  triggered_at: string
  acknowledged_at: string | null
  acknowledged_by: string | null
  resolved_at: string | null
  resolved_by: string | null
  created_at: string
  updated_at: string
}

// Session 018 — WOW #4: Predictive Risk Trajectory. Deterministic
// extrapolation of the Risk Engine's own trend factor (never a second
// model) — see `app/services/risk_engine.py::compute_risk_trajectory`.
export interface TrajectoryPoint {
  hours_ahead: number
  projected_at: string
  score: number
  severity: RiskSeverity
  projected_water_level_mm: number | null
}

export interface RiskTrajectory {
  current_score: number
  current_severity: RiskSeverity
  points: TrajectoryPoint[]
  trend_rate_mm_per_hour: number | null
  basis: 'rising_trend' | 'flat_or_falling' | 'insufficient_data'
  computed_at: string
  // Same city-selector honesty convention as RiskScore/EnvironmentalSummary.
  data_available: boolean
  planned_data_source: string | null
}

// --- P3: AI Resilience Intelligence ---

export type SituationLevel = 'low' | 'moderate' | 'high' | 'critical'

export interface SituationBrief {
  id: string
  generated_at: string
  language: string
  triggered_by: 'scheduled' | 'manual' | 'event'
  situation: SituationLevel
  summary: string
  drivers: string[]
  zones_to_watch: string[]
  recommendations: string[]
  confidence: number
  limitations: string[]
  risk_score_snapshot: number
  risk_severity_snapshot: RiskSeverity
  provider: string
  model: string
}

export interface AIIntelligenceStatus {
  is_configured: boolean
  scheduled_analysis_interval_minutes: number
  daily_request_ceiling: number
  requests_today: number
  cooldown_seconds: number
  event_triggered_enabled: boolean
  last_analysis_at: string | null
  next_analysis_at: string | null
  last_analysis_error: string | null
}

export interface TriggerAnalysisResult {
  ok: boolean
  message: string
  brief: SituationBrief | null
}

// --- P4: Scenario Simulator ---

export interface ScenarioWarningPreview {
  would_trigger: boolean
  severity: RiskSeverity | null
  message: string | null
}

export interface ScenarioAIExplanation {
  explanation: string
  resilience_recommendations: string[]
  confidence: number
}

export interface ScenarioSimulateRequest {
  rainfall_adjustment_pct: number
  river_level_adjustment_pct: number
  language?: string
  include_ai_explanation?: boolean
  // Session 019 — WOW #2: same city-selector honesty pattern as
  // GET /risk/current. Omitted => today's unchanged single-city behavior.
  city_id?: string | null
}

export interface ScenarioSimulateResponse {
  current: RiskScore
  projected: RiskScore
  rainfall_adjustment_pct: number
  river_level_adjustment_pct: number
  water_level_mm_current: number | null
  water_level_mm_projected: number | null
  precipitation_24h_mm_current: number | null
  precipitation_24h_mm_projected: number | null
  projected_warning: ScenarioWarningPreview
  ai_explanation: ScenarioAIExplanation | null
  ai_explanation_error: string | null
}
