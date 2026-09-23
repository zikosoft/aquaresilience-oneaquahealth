import type { RiskSeverity } from '@/types'

// Shared by the Command Center's "Current Warning" widget and the Early
// Warnings page, so a severity always renders with the same color
// everywhere. Deliberately mirrors the quartile bands already used by the
// RiskGauge widget (green/amber/orange/red).
const SEVERITY_COLOR: Record<RiskSeverity, string> = {
  LOW: 'success',
  MODERATE: 'warning',
  HIGH: 'orange-darken-2',
  CRITICAL: 'error',
}

export function severityColor(severity: RiskSeverity | string): string {
  return SEVERITY_COLOR[severity as RiskSeverity] ?? 'medium-emphasis'
}
