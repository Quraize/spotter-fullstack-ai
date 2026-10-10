import { describe, expect, it } from 'vitest'

import { planFixture } from '../test/fixtures/plan'
import {
  HEATMAP_INTENSITY,
  clampHour,
  heatmapColorExpression,
  heatmapFeatures,
  heatmapRadiusExpression,
  heatmapWeightExpression,
  hourProperty,
  levelAtHour,
  withAlpha,
} from './heatmap'
import { LEVELS, LEVEL_BY_KEY } from './risk'

// Loosely typed view of a MapLibre expression for assertions.
type Expr = unknown[]

describe('hourProperty / clampHour', () => {
  it('names the per-hour feature property', () => {
    expect(hourProperty(0)).toBe('h0')
    expect(hourProperty(48)).toBe('h48')
  })

  it('rejects hours outside the 0-48 window or non-integers', () => {
    expect(() => hourProperty(-1)).toThrow(RangeError)
    expect(() => hourProperty(49)).toThrow(RangeError)
    expect(() => hourProperty(1.5)).toThrow(RangeError)
  })

  it('clamps and rounds slider values into the window', () => {
    expect(clampHour(-3)).toBe(0)
    expect(clampHour(60)).toBe(48)
    expect(clampHour(6.4)).toBe(6)
    expect(clampHour(Number.NaN)).toBe(0)
    expect(clampHour(10, 5)).toBe(5)
  })
})

describe('heatmapFeatures', () => {
  it('turns every heatmap point into a Point feature with one property per hour', () => {
    const fc = heatmapFeatures(planFixture.heatmap)
    expect(fc.type).toBe('FeatureCollection')
    expect(fc.features).toHaveLength(2)
    const [first, second] = fc.features
    expect(first.geometry).toEqual({ type: 'Point', coordinates: [-87.6324, 41.8832] })
    expect(Object.keys(first.properties)).toHaveLength(49)
    expect(first.properties.h0).toBe(0)
    expect(second.properties.h3).toBe(0)
    expect(second.properties.h4).toBe(4)
    expect(second.properties.h6).toBe(4)
    expect(second.properties.h7).toBe(0)
  })

  it('tolerates points with fewer levels than hours by leaving those hours undefined', () => {
    const fc = heatmapFeatures({ interval_miles: 25, hours: planFixture.heatmap.hours, points: [{ lat: 1, lon: 2, levels: [3] }] })
    expect(fc.features[0].properties.h0).toBe(3)
    expect(fc.features[0].properties).not.toHaveProperty('h1')
  })
})

describe('levelAtHour', () => {
  it('reads the level for an hour, falling back to Low when missing', () => {
    const point = planFixture.heatmap.points[1]
    expect(levelAtHour(point, 5).key).toBe('no_travel')
    expect(levelAtHour(point, 0).key).toBe('low')
    expect(levelAtHour({ lat: 0, lon: 0, levels: [] }, 3).key).toBe('low')
  })
})

describe('heatmapWeightExpression', () => {
  it('weights a point 1 when its level at the hour matches the layer level, else 0', () => {
    const expr = heatmapWeightExpression(6, LEVEL_BY_KEY.severe.value) as Expr
    expect(expr).toEqual(['match', ['get', 'h6'], 3, 1, 0])
  })
})

describe('withAlpha', () => {
  it('converts hex colours to rgba', () => {
    expect(withAlpha('#2e7d32', 0.5)).toBe('rgba(46,125,50,0.5)')
    expect(withAlpha('#FFFFFF', 1)).toBe('rgba(255,255,255,1)')
  })

  it('rejects malformed colours', () => {
    expect(() => withAlpha('red', 1)).toThrow()
  })
})

describe('heatmapColorExpression', () => {
  it('ramps heatmap density from transparent to the level colour', () => {
    for (const level of LEVELS) {
      const expr = heatmapColorExpression(level) as Expr
      expect(expr.slice(0, 3)).toEqual(['interpolate', ['linear'], ['heatmap-density']])
      const stops = expr.slice(3)
      expect(stops.length % 2).toBe(0)
      const densities = stops.filter((_, i) => i % 2 === 0) as number[]
      const colours = stops.filter((_, i) => i % 2 === 1) as string[]
      expect(densities[0]).toBe(0)
      expect(densities.at(-1)).toBe(1)
      for (let i = 1; i < densities.length; i++) expect(densities[i]).toBeGreaterThan(densities[i - 1])
      expect(colours[0]).toBe(withAlpha(level.color, 0))
      for (const c of colours) expect(c.startsWith(withAlpha(level.color, 0).slice(0, -2))).toBe(true)
    }
  })

  it('draws Low fainter than the dangerous levels', () => {
    const alpha = (level: (typeof LEVELS)[number]) => {
      const expr = heatmapColorExpression(level) as Expr
      return Number(String(expr.at(-1)).match(/,([\d.]+)\)$/)![1])
    }
    expect(alpha(LEVEL_BY_KEY.low)).toBeLessThan(alpha(LEVEL_BY_KEY.moderate))
    expect(alpha(LEVEL_BY_KEY.no_travel)).toBeGreaterThanOrEqual(alpha(LEVEL_BY_KEY.severe))
  })
})

describe('heatmapRadiusExpression', () => {
  it('scales the radius with zoom so a blob covers about one sampling interval on the ground', () => {
    const expr = heatmapRadiusExpression(25, 0) as Expr
    expect(expr.slice(0, 3)).toEqual(['interpolate', ['exponential', 2], ['zoom']])
    const stops = expr.slice(3) as number[]
    expect(stops).toHaveLength(4)
    const [zMin, rMin, zMax, rMax] = stops
    // 25 miles at the equator on MapLibre's 512 px tiles: 25 * 1609.344 / 78271.517 px at zoom 0.
    const r0 = (25 * 1609.344) / 78271.517
    expect(rMin).toBe(4)
    expect(zMin).toBeCloseTo(Math.log2(4 / r0), 5)
    expect(zMax).toBe(10)
    expect(rMax).toBeCloseTo(r0 * 2 ** 10, 3)
  })

  it('grows the radius at higher latitudes where a mile spans more pixels', () => {
    const atEquator = (heatmapRadiusExpression(25, 0) as Expr).at(-1) as number
    const atDenver = (heatmapRadiusExpression(25, 40) as Expr).at(-1) as number
    expect(atDenver).toBeCloseTo(atEquator / Math.cos((40 * Math.PI) / 180), 6)
  })

  it('is proportional to the sampling interval', () => {
    const r25 = (heatmapRadiusExpression(25, 40) as Expr).at(-1) as number
    const r50 = (heatmapRadiusExpression(50, 40) as Expr).at(-1) as number
    expect(r50).toBeCloseTo(r25 * 2, 6)
  })

  it('keeps a minimum legible radius when the interval is tiny at zoom 0', () => {
    const [zMin, rMin] = (heatmapRadiusExpression(10, 0) as Expr).slice(3) as number[]
    expect(rMin).toBe(4)
    expect(zMin).toBeGreaterThan(0)
  })
})

describe('HEATMAP_INTENSITY', () => {
  it('makes the centre density of an isolated weight-1 point exactly 1 (MapLibre Gaussian coefficient)', () => {
    expect(HEATMAP_INTENSITY * 0.3989422804014327).toBeCloseTo(1, 9)
  })
})
