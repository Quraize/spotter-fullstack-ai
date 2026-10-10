// Mirrors the JSON produced by backend/api/planner.py.

export type LevelKey = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'

export type SampleInterval = 10 | 25 | 50

export interface PlanRequest {
  origin: string
  destination: string
  departure_time: string // ISO 8601 with UTC offset
  load_weight_lb: number
  sample_interval_miles: SampleInterval
}

export interface Place {
  query: string
  name: string
  lat: number
  lon: number
}

export interface Checkpoint {
  index: number
  mile: number
  lat: number
  lon: number
  eta: string
  wind_mph: number
  gust_mph: number | null
  rain_in_hr: number
  snow_in_hr: number
  wind_level: LevelKey
  rain_level: LevelKey
  snow_level: LevelKey
  level: LevelKey
  load_rule: string | null
  reason: string
}

export interface RouteSummary {
  miles_by_level: Record<LevelKey, number>
  total_miles: number
  average_risk: number
  worst_level: LevelKey
  worst_checkpoint_index: number
  no_travel: boolean
}

export interface Route {
  id: string
  name: string
  provider_index: number
  rank: number
  distance_miles: number
  duration_seconds: number
  traffic_delay_seconds: number
  departure_time: string
  arrival_time: string
  geometry: [number, number][] // [lon, lat]
  bbox: [number, number, number, number] // [minLon, minLat, maxLon, maxLat]
  checkpoints: Checkpoint[]
  summary: RouteSummary
}

export interface Recommendation {
  route_id: string | null
  ranked_ids: string[]
  reason: string
  all_no_travel: boolean
}

export interface HeatmapPoint {
  lat: number
  lon: number
  levels: number[] // 49 values, hour 0 = departure
}

export interface Heatmap {
  interval_miles: number
  hours: string[]
  points: HeatmapPoint[]
}

export interface Plan {
  inputs: {
    origin: Place
    destination: Place
    departure_time: string
    load_weight_lb: number
    sample_interval_miles: number
  }
  routes: Route[]
  recommended_route_id: string | null
  recommendation: Recommendation
  heatmap: Heatmap
  warnings: string[]
}
