import type { FeatureCollection, LineString, Point } from 'geojson'

import type { LevelKey, Route } from '../api/types'

export interface RouteProps {
  id: string
  name: string
  rank: number
  selected: boolean
  recommended: boolean
}

export interface CheckpointProps {
  route_id: string
  route_name: string
  index: number
  mile: number
  eta: string
  level: LevelKey
  wind_mph: number
  gust_mph: number | null
  rain_in_hr: number
  snow_in_hr: number
  reason: string
  selected: boolean
}

/** Non-selected routes first so the selected one is drawn on top. */
function selectedLast(routes: Route[], selectedId: string | null): Route[] {
  return [...routes].sort((a, b) => Number(a.id === selectedId) - Number(b.id === selectedId))
}

export function routeFeatures(
  routes: Route[],
  selectedId: string | null,
  recommendedId: string | null,
): FeatureCollection<LineString, RouteProps> {
  return {
    type: 'FeatureCollection',
    features: selectedLast(routes, selectedId).map((route) => ({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: route.geometry },
      properties: {
        id: route.id,
        name: route.name,
        rank: route.rank,
        selected: route.id === selectedId,
        recommended: route.id === recommendedId,
      },
    })),
  }
}

export function checkpointFeatures(routes: Route[], selectedId: string | null): FeatureCollection<Point, CheckpointProps> {
  return {
    type: 'FeatureCollection',
    features: selectedLast(routes, selectedId).flatMap((route) =>
      route.checkpoints.map((c) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [c.lon, c.lat] },
        properties: {
          route_id: route.id,
          route_name: route.name,
          index: c.index,
          mile: c.mile,
          eta: c.eta,
          level: c.level,
          wind_mph: c.wind_mph,
          gust_mph: c.gust_mph,
          rain_in_hr: c.rain_in_hr,
          snow_in_hr: c.snow_in_hr,
          reason: c.reason,
          selected: route.id === selectedId,
        },
      })),
    ),
  }
}

/** Union of the routes' bounding boxes as [[minLon, minLat], [maxLon, maxLat]]. */
export function planBounds(routes: Route[]): [[number, number], [number, number]] | null {
  if (routes.length === 0) return null
  let [minLon, minLat, maxLon, maxLat] = routes[0].bbox
  for (const route of routes.slice(1)) {
    const [a, b, c, d] = route.bbox
    minLon = Math.min(minLon, a)
    minLat = Math.min(minLat, b)
    maxLon = Math.max(maxLon, c)
    maxLat = Math.max(maxLat, d)
  }
  return [
    [minLon, minLat],
    [maxLon, maxLat],
  ]
}
