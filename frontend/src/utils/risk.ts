import type { RiskFactor, RiskSeverity, WarningFactorSnapshot } from '@/types'

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

// i18n note: the backend never sends a display label for a risk factor —
// only its stable `key` ("rainfall" | "hydrology" | "environmental" |
// "trend"), which every screen resolves through common.riskFactors.<key>.
// This is what lets the Risk Factor Contribution chart and the Early
// Warning message translate correctly instead of leaking the backend's
// English-only RiskFactor.label / WarningFactorSnapshot.label strings.
export function factorTranslationKey(key: string): string {
  return `common.riskFactors.${key}`
}

// Finds the factor with the highest contribution, from either shape the
// API returns it in: RiskScore.factors (an array, each entry carrying its
// own `key`) or EarlyWarning.factors (a Record keyed by factor key). Used
// to reconstruct "leading factor: <X>" client-side instead of trusting the
// backend's pre-rendered English sentence.
export function leadingFactorKey(
  factors: RiskFactor[] | Record<string, WarningFactorSnapshot> | null | undefined,
): string | null {
  if (!factors) return null
  const entries: [string, number][] = Array.isArray(factors)
    ? factors.map((f) => [f.key, f.contribution])
    : Object.entries(factors).map(([key, f]) => [key, f.contribution])
  if (!entries.length) return null
  return entries.reduce((best, cur) => (cur[1] > best[1] ? cur : best))[0]
}
