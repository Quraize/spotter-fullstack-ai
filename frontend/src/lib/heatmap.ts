// Heatmap data and MapLibre expressions for the 0-48 h forecast slider.
//
// The backend sends, for every unique checkpoint, the risk level (0 Low to
// 4 No Travel) at each hour from departure to departure + 48 h. Each point
// becomes one GeoJSON feature with properties h0..h48, so moving the slider
// only swaps which property the layers read: no new data, no network.
//
// One MapLibre heatmap layer per level, not one layer with a density ramp:
// a density ramp adds overlapping blobs together, so two Moderate points
// close to each other would render as High. With one layer per level a
// point only contributes to the layer of its own level, density saturates
// at that level's colour, and the layers stack worst-on-top.

import type { FeatureCollection, Point } from 'geojson'
import type { ExpressionSpecification } from 'maplibre-gl'

import type { Heatmap, HeatmapPoint } from '../api/types'
import { levelFromValue, type LevelMeta } from './risk'

export const HEATMAP_HOURS = 48

// MapLibre's heatmap kernel is weight * intensity * GAUSS_COEF * exp(-4.5 d^2)
// with GAUSS_COEF = 1/sqrt(2*pi); this intensity makes the centre density of
// an isolated weight-1 point exactly 1, i.e. the top of the colour ramp.
export const HEATMAP_INTENSITY = Math.sqrt(2 * Math.PI)

const METERS_PER_MILE = 1609.344
// MapLibre uses 512 px tiles: at zoom 0 the equator spans 512 px.
const EQUATOR_METERS_PER_PIXEL_Z0 = 40075016.686 / 512
const RADIUS_INTERVALS = 1 // blob radius in sampling intervals; 1 keeps adjacent blobs merged
const MIN_RADIUS_PX = 4
const MAX_RADIUS_ZOOM = 10 // beyond this the radius stays fixed to bound fragment work
// Alpha at full density, per level. Low is deliberately faint: it is context, not a warning.
const MAX_ALPHA: Record<LevelMeta['key'], number> = { low: 0.32, moderate: 0.62, high: 0.68, severe: 0.74, no_travel: 0.8 }

export type HeatmapProps = Record<string, number>

export function hourProperty(hour: number): string {
  if (!Number.isInteger(hour) || hour < 0 || hour > HEATMAP_HOURS) {
    throw new RangeError(`hour must be an integer between 0 and ${HEATMAP_HOURS}, got ${hour}`)
  }
  return `h${hour}`
}

export function clampHour(hour: number, maxHour = HEATMAP_HOURS): number {
  if (!Number.isFinite(hour)) return 0
  return Math.min(maxHour, Math.max(0, Math.round(hour)))
}

export function heatmapFeatures(heatmap: Heatmap): FeatureCollection<Point, HeatmapProps> {
  return {
    type: 'FeatureCollection',
    features: heatmap.points.map((p) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: Object.fromEntries(p.levels.map((level, hour) => [`h${hour}`, level])),
    })),
  }
}

export function levelAtHour(point: HeatmapPoint, hour: number): LevelMeta {
  return levelFromValue(point.levels[hour] ?? 0)
}

/** Weight 1 for points whose level at `hour` is `levelValue`, else 0. */
export function heatmapWeightExpression(hour: number, levelValue: number): ExpressionSpecification {
  const expression: unknown = ['match', ['get', hourProperty(hour)], levelValue, 1, 0]
  return expression as ExpressionSpecification
}

export function withAlpha(hex: string, alpha: number): string {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex)
  if (!match) throw new Error(`Expected a #rrggbb colour, got ${hex}`)
  const [r, g, b] = match.slice(1).map((h) => parseInt(h, 16))
  return `rgba(${r},${g},${b},${alpha})`
}

/** Density ramp from transparent to the level's colour; saturates so overlaps never change hue. */
export function heatmapColorExpression(level: LevelMeta): ExpressionSpecification {
  const a = MAX_ALPHA[level.key]
  const expression: unknown = [
    'interpolate',
    ['linear'],
    ['heatmap-density'],
    0,
    withAlpha(level.color, 0),
    0.08,
    withAlpha(level.color, round3(a * 0.15)),
    0.45,
    withAlpha(level.color, round3(a * 0.8)),
    1,
    withAlpha(level.color, a),
  ]
  return expression as ExpressionSpecification
}

/**
 * Radius in screen pixels that spans one sampling interval on the ground at
 * `latitudeDeg`, growing with 2^zoom (exact under exponential-2 interpolation),
 * never below MIN_RADIUS_PX and frozen above MAX_RADIUS_ZOOM.
 */
export function heatmapRadiusExpression(intervalMiles: number, latitudeDeg: number): ExpressionSpecification {
  const metersPerPixelZ0 = EQUATOR_METERS_PER_PIXEL_Z0 * Math.cos((latitudeDeg * Math.PI) / 180)
  const radiusZ0 = (RADIUS_INTERVALS * intervalMiles * METERS_PER_MILE) / metersPerPixelZ0
  const zoomAtMin = Math.log2(MIN_RADIUS_PX / radiusZ0)
  const stops =
    zoomAtMin > 0 && zoomAtMin < MAX_RADIUS_ZOOM
      ? [zoomAtMin, MIN_RADIUS_PX, MAX_RADIUS_ZOOM, radiusZ0 * 2 ** MAX_RADIUS_ZOOM]
      : [0, Math.max(MIN_RADIUS_PX, radiusZ0), MAX_RADIUS_ZOOM, Math.max(MIN_RADIUS_PX, radiusZ0 * 2 ** MAX_RADIUS_ZOOM)]
  const expression: unknown = ['interpolate', ['exponential', 2], ['zoom'], ...stops]
  return expression as ExpressionSpecification
}

function round3(n: number): number {
  return Math.round(n * 1000) / 1000
}
