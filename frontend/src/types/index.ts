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

export interface AppSetting {
  category: string
  key: string
  value: Record<string, unknown>
  description: string
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
