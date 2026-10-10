import { describe, expect, it } from 'vitest'

import { LEVELS, LEVEL_BY_KEY, levelColor, levelColorExpression, levelFromValue } from './risk'

describe('LEVELS', () => {
  it('lists the five PDF levels in order with values 0 to 4', () => {
    expect(LEVELS.map((l) => l.key)).toEqual(['low', 'moderate', 'high', 'severe', 'no_travel'])
    expect(LEVELS.map((l) => l.value)).toEqual([0, 1, 2, 3, 4])
    expect(LEVELS.map((l) => l.label)).toEqual(['Low', 'Moderate', 'High', 'Severe', 'No Travel'])
  })

  it('has a distinct hex colour per level', () => {
    const colours = LEVELS.map((l) => l.color)
    expect(new Set(colours).size).toBe(5)
    for (const c of colours) expect(c).toMatch(/^#[0-9a-f]{6}$/i)
  })

  it('is indexable by key', () => {
    expect(LEVEL_BY_KEY.severe.label).toBe('Severe')
    expect(levelColor('no_travel')).toBe(LEVEL_BY_KEY.no_travel.color)
  })
})

describe('levelFromValue', () => {
  it('maps the heatmap integer scale back to a level, rounding to nearest', () => {
    expect(levelFromValue(0).key).toBe('low')
    expect(levelFromValue(4).key).toBe('no_travel')
    expect(levelFromValue(2.6).key).toBe('severe')
    expect(levelFromValue(9).key).toBe('no_travel')
    expect(levelFromValue(-1).key).toBe('low')
  })
})

describe('levelColorExpression', () => {
  it('builds a MapLibre match expression over the level property', () => {
    const expr = levelColorExpression() as unknown as unknown[]
    expect(expr[0]).toBe('match')
    expect(expr[1]).toEqual(['get', 'level'])
    for (const level of LEVELS) {
      const i = expr.indexOf(level.key)
      expect(i).toBeGreaterThan(1)
      expect(expr[i + 1]).toBe(level.color)
    }
    expect(expr).toHaveLength(2 + LEVELS.length * 2 + 1) // plus fallback colour
  })
})
