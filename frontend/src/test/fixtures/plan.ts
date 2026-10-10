import type { Checkpoint, LevelKey, Plan, Route } from '../../api/types'

const DEPART = '2026-10-11T08:00:00-05:00'

function checkpoint(index: number, mile: number, lat: number, lon: number, eta: string, level: LevelKey, wind = 10): Checkpoint {
  const labels: Record<LevelKey, string> = {
    low: 'Low',
    moderate: 'Moderate',
    high: 'High',
    severe: 'Severe',
    no_travel: 'No Travel',
  }
  return {
    index,
    mile,
    lat,
    lon,
    eta,
    wind_mph: wind,
    gust_mph: wind + 8,
    rain_in_hr: 0,
    snow_in_hr: 0,
    wind_level: level,
    rain_level: 'low',
    snow_level: 'low',
    level,
    load_rule: level === 'no_travel' ? 'load 42,000 lb exceeds 30,000 lb in 45-54 mph wind: No Travel' : null,
    reason: `Wind ${wind} mph: ${labels[level]}`,
  }
}

function summary(miles: Partial<Record<LevelKey, number>>, worst: LevelKey, worstIndex: number, avg: number): Route['summary'] {
  const by: Record<LevelKey, number> = { low: 0, moderate: 0, high: 0, severe: 0, no_travel: 0, ...miles }
  return {
    miles_by_level: by,
    total_miles: Object.values(by).reduce((a, b) => a + b, 0),
    average_risk: avg,
    worst_level: worst,
    worst_checkpoint_index: worstIndex,
    no_travel: by.no_travel > 0,
  }
}

export const routeOne: Route = {
  id: 'r1',
  name: 'Route 1',
  provider_index: 0,
  rank: 2,
  distance_miles: 1008.4,
  duration_seconds: 50040,
  traffic_delay_seconds: 120,
  departure_time: DEPART,
  arrival_time: '2026-10-11T21:54:00-05:00',
  geometry: [
    [-87.6324, 41.8832],
    [-95.9, 41.25],
    [-104.9849, 39.7385],
  ],
  bbox: [-104.9849, 39.7385, -87.6324, 41.8832],
  checkpoints: [
    checkpoint(0, 0, 41.8832, -87.6324, DEPART, 'low'),
    checkpoint(1, 500, 41.25, -95.9, '2026-10-11T15:02:00-05:00', 'moderate', 28),
    checkpoint(2, 1008.4, 39.7385, -104.9849, '2026-10-11T21:54:00-05:00', 'low'),
  ],
  summary: summary({ low: 908.4, moderate: 100 }, 'moderate', 1, 0.099),
}

export const routeTwo: Route = {
  id: 'r2',
  name: 'Route 2',
  provider_index: 1,
  rank: 1,
  distance_miles: 1143.2,
  duration_seconds: 56628,
  traffic_delay_seconds: 0,
  departure_time: DEPART,
  arrival_time: '2026-10-11T23:43:48-05:00',
  geometry: [
    [-87.6324, 41.8832],
    [-96.7, 40.8],
    [-104.9849, 39.7385],
  ],
  bbox: [-104.9849, 39.7385, -87.6324, 41.8832],
  checkpoints: [
    checkpoint(0, 0, 41.8832, -87.6324, DEPART, 'low'),
    checkpoint(1, 500, 40.8, -96.7, '2026-10-11T16:10:00-05:00', 'low'),
    checkpoint(2, 1143.2, 39.7385, -104.9849, '2026-10-11T23:43:48-05:00', 'low'),
  ],
  summary: summary({ low: 1143.2 }, 'low', 0, 0),
}

export const routeThree: Route = {
  id: 'r3',
  name: 'Route 3',
  provider_index: 2,
  rank: 3,
  distance_miles: 1324.2,
  duration_seconds: 67176,
  traffic_delay_seconds: 0,
  departure_time: DEPART,
  arrival_time: '2026-10-12T02:39:36-05:00',
  geometry: [
    [-87.6324, 41.8832],
    [-97.5, 38.9],
    [-104.9849, 39.7385],
  ],
  bbox: [-104.9849, 38.9, -87.6324, 41.8832],
  checkpoints: [
    checkpoint(0, 0, 41.8832, -87.6324, DEPART, 'low'),
    checkpoint(1, 500, 38.9, -97.5, '2026-10-11T17:30:00-05:00', 'no_travel', 50),
    checkpoint(2, 1324.2, 39.7385, -104.9849, '2026-10-12T02:39:36-05:00', 'low'),
  ],
  summary: summary({ low: 824.2, no_travel: 500 }, 'no_travel', 1, 1.51),
}

export const hours = Array.from({ length: 49 }, (_, h) => {
  const d = new Date(Date.UTC(2026, 9, 11, 13 + h, 0, 0))
  const local = new Date(d.getTime() - 5 * 3600 * 1000)
  return local.toISOString().replace('.000Z', '-05:00')
})

export const planFixture: Plan = {
  inputs: {
    origin: { query: 'Chicago, IL', name: 'Chicago, IL', lat: 41.8832, lon: -87.6324 },
    destination: { query: 'Denver, CO', name: 'Denver, CO', lat: 39.7385, lon: -104.9849 },
    departure_time: DEPART,
    load_weight_lb: 42000,
    sample_interval_miles: 25,
  },
  routes: [routeOne, routeTwo, routeThree],
  recommended_route_id: 'r2',
  recommendation: {
    route_id: 'r2',
    ranked_ids: ['r2', 'r1', 'r3'],
    reason: 'Lowest average risk: 0.00 vs 0.10 on the next best route. 1 route not recommended because of No Travel conditions.',
    all_no_travel: false,
  },
  heatmap: {
    interval_miles: 25,
    hours,
    points: [
      { lat: 41.8832, lon: -87.6324, levels: hours.map(() => 0) },
      { lat: 38.9, lon: -97.5, levels: hours.map((_, h) => (h >= 4 && h <= 6 ? 4 : 0)) },
    ],
  },
  warnings: [],
}

export function planWith(overrides: Partial<Plan>): Plan {
  return { ...planFixture, ...overrides }
}
