import type { ExpressionSpecification } from 'maplibre-gl'

import type { LevelKey } from '../api/types'

export interface LevelMeta {
  key: LevelKey
  label: string
  value: number
  color: string
}

// Same order and values as backend/routing/risk.py.
export const LEVELS: LevelMeta[] = [
  { key: 'low', label: 'Low', value: 0, color: '#2e7d32' },
  { key: 'moderate', label: 'Moderate', value: 1, color: '#f9a825' },
  { key: 'high', label: 'High', value: 2, color: '#ef6c00' },
  { key: 'severe', label: 'Severe', value: 3, color: '#c62828' },
  { key: 'no_travel', label: 'No Travel', value: 4, color: '#4a148c' },
]

export const LEVEL_BY_KEY = Object.fromEntries(LEVELS.map((l) => [l.key, l])) as Record<LevelKey, LevelMeta>

export function levelColor(key: LevelKey): string {
  return LEVEL_BY_KEY[key].color
}

/** Heatmap values are integers 0-4; tolerate anything numeric. */
export function levelFromValue(value: number): LevelMeta {
  const index = Math.min(LEVELS.length - 1, Math.max(0, Math.round(value)))
  return LEVELS[index]
}

const FALLBACK_COLOR = '#9e9e9e'

/** MapLibre expression: colour a feature by its `level` property. */
export function levelColorExpression(): ExpressionSpecification {
  const expression: unknown = ['match', ['get', 'level'], ...LEVELS.flatMap((l) => [l.key, l.color]), FALLBACK_COLOR]
  return expression as ExpressionSpecification
}
