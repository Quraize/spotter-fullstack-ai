import { describe, expect, it } from 'vitest'

import { planFixture } from '../test/fixtures/plan'
import { checkpointFeatures, planBounds, routeFeatures } from './geojson'

describe('routeFeatures', () => {
  it('makes one LineString per route with display properties', () => {
    const fc = routeFeatures(planFixture.routes, 'r2', 'r2')
    expect(fc.type).toBe('FeatureCollection')
    expect(fc.features).toHaveLength(3)
    for (const f of fc.features) {
      expect(f.geometry.type).toBe('LineString')
      const route = planFixture.routes.find((r) => r.id === f.properties.id)!
      expect(f.geometry.coordinates).toEqual(route.geometry)
      expect(f.properties).toMatchObject({ name: route.name, rank: route.rank })
    }
  })

  it('flags the selected and recommended routes and draws the selected one last', () => {
    const fc = routeFeatures(planFixture.routes, 'r1', 'r2')
    const byId = Object.fromEntries(fc.features.map((f) => [f.properties.id, f.properties]))
    expect(byId.r1).toMatchObject({ selected: true, recommended: false })
    expect(byId.r2).toMatchObject({ selected: false, recommended: true })
    expect(byId.r3).toMatchObject({ selected: false, recommended: false })
    expect(fc.features[fc.features.length - 1].properties.id).toBe('r1')
  })

  it('handles no selection', () => {
    const fc = routeFeatures(planFixture.routes, null, null)
    expect(fc.features.every((f) => !f.properties.selected && !f.properties.recommended)).toBe(true)
  })
})

describe('checkpointFeatures', () => {
  it('makes one Point per checkpoint with everything the popup needs', () => {
    const fc = checkpointFeatures(planFixture.routes, 'r2')
    const total = planFixture.routes.reduce((n, r) => n + r.checkpoints.length, 0)
    expect(fc.features).toHaveLength(total)
    const f = fc.features.find((x) => x.properties.route_id === 'r3' && x.properties.index === 1)!
    expect(f.geometry).toEqual({ type: 'Point', coordinates: [-97.5, 38.9] })
    expect(f.properties).toMatchObject({
      route_id: 'r3',
      route_name: 'Route 3',
      index: 1,
      mile: 500,
      eta: '2026-10-11T17:30:00-05:00',
      level: 'no_travel',
      wind_mph: 50,
      gust_mph: 58,
      rain_in_hr: 0,
      snow_in_hr: 0,
      reason: 'Wind 50 mph: No Travel',
      selected: false,
    })
  })

  it('puts the selected route’s checkpoints last so they render on top', () => {
    const fc = checkpointFeatures(planFixture.routes, 'r1')
    const last = fc.features.slice(-3)
    expect(last.every((f) => f.properties.route_id === 'r1' && f.properties.selected)).toBe(true)
  })
})

describe('planBounds', () => {
  it('unions the route bounding boxes', () => {
    expect(planBounds(planFixture.routes)).toEqual([
      [-104.9849, 38.9],
      [-87.6324, 41.8832],
    ])
  })

  it('is null without routes', () => {
    expect(planBounds([])).toBeNull()
  })
})
