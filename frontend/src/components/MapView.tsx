import 'maplibre-gl/dist/maplibre-gl.css'

import type { FeatureCollection } from 'geojson'
import {
  setWorkerUrl,
  type CircleLayerSpecification,
  type ExpressionSpecification,
  type HeatmapLayerSpecification,
  type LineLayerSpecification,
} from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Layer,
  Map,
  Marker,
  NavigationControl,
  Popup,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
} from 'react-map-gl/maplibre'

import type { Plan } from '../api/types'
import { formatDateTime } from '../lib/format'
import { checkpointFeatures, planBounds, routeFeatures, type CheckpointProps } from '../lib/geojson'
import {
  HEATMAP_INTENSITY,
  clampHour,
  heatmapColorExpression,
  heatmapFeatures,
  heatmapRadiusExpression,
  heatmapWeightExpression,
} from '../lib/heatmap'
import { LEVELS, LEVEL_BY_KEY, levelColorExpression } from '../lib/risk'

// Free vector tiles, no key, no request limits: https://openfreemap.org
const MAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'

// Bundled by Vite as its own ES-module worker so the production build ships it.
setWorkerUrl(maplibreWorkerUrl)

declare global {
  interface Window {
    __spotterMap?: ReturnType<MapRef['getMap']>
  }
}

const SELECTED_COLOR = '#1565c0'
const OTHER_COLOR = '#90a4ae'

const routeCasingPaint: LineLayerSpecification['paint'] = {
  'line-color': '#ffffff',
  'line-width': ['case', ['get', 'selected'], 9, 6],
  'line-opacity': 0.9,
}

const routeLinePaint: LineLayerSpecification['paint'] = {
  'line-color': ['case', ['get', 'selected'], SELECTED_COLOR, OTHER_COLOR],
  'line-width': ['case', ['get', 'selected'], 5, 3],
}

const lineLayout: LineLayerSpecification['layout'] = { 'line-cap': 'round', 'line-join': 'round' }

const checkpointPaint: CircleLayerSpecification['paint'] = {
  'circle-color': levelColorExpression(),
  'circle-radius': [
    'interpolate',
    ['linear'],
    ['zoom'],
    3,
    ['case', ['get', 'selected'], 4.5, 3],
    8,
    ['case', ['get', 'selected'], 9, 6],
  ],
  'circle-stroke-color': '#ffffff',
  'circle-stroke-width': ['case', ['get', 'selected'], 1.5, 1],
  'circle-opacity': ['case', ['get', 'selected'], 1, 0.55],
  'circle-stroke-opacity': ['case', ['get', 'selected'], 1, 0.55],
}

// Colour ramps never change, so build them once.
const heatmapColors = Object.fromEntries(LEVELS.map((l) => [l.key, heatmapColorExpression(l)]))

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

interface Props {
  plan: Plan | null
  selectedId: string | null
  onSelect: (id: string) => void
  /** Forecast hour after departure (0-48) shown by the heatmap. */
  hour: number
  showHeatmap: boolean
  showCheckpoints: boolean
}

interface Hovered extends CheckpointProps {
  lon: number
  lat: number
}

export function MapView({ plan, selectedId, onSelect, hour, showHeatmap, showCheckpoints }: Props) {
  const mapRef = useRef<MapRef>(null)
  const [hovered, setHovered] = useState<Hovered | null>(null)
  const [cursor, setCursor] = useState<string>('grab')

  const routes = useMemo(
    () => (plan ? routeFeatures(plan.routes, selectedId, plan.recommended_route_id) : EMPTY),
    [plan, selectedId],
  )
  const checkpoints = useMemo(() => (plan ? checkpointFeatures(plan.routes, selectedId) : EMPTY), [plan, selectedId])
  const heatmap = useMemo(() => (plan ? heatmapFeatures(plan.heatmap) : EMPTY), [plan])
  const heatmapRadius = useMemo<ExpressionSpecification | number>(() => {
    const bounds = plan ? planBounds(plan.routes) : null
    if (!plan || !bounds) return 10
    return heatmapRadiusExpression(plan.heatmap.interval_miles, (bounds[0][1] + bounds[1][1]) / 2)
  }, [plan])
  const heatmapHour = clampHour(hour, plan ? plan.heatmap.hours.length - 1 : 0)

  useEffect(() => {
    if (!plan) return
    const bounds = planBounds(plan.routes)
    if (bounds) mapRef.current?.fitBounds(bounds, { padding: 60, duration: 900 })
  }, [plan])

  // Dev-only hook for browser-driven tests (project coordinates, query features).
  function exposeMapForTests() {
    if (import.meta.env.DEV && mapRef.current) window.__spotterMap = mapRef.current.getMap()
  }

  function hoveredFromEvent(event: MapLayerMouseEvent): Hovered | null {
    const feature = event.features?.find((f) => f.layer.id === 'checkpoints')
    if (!feature || feature.geometry.type !== 'Point') return null
    const [lon, lat] = feature.geometry.coordinates
    return { ...(feature.properties as CheckpointProps), lon, lat }
  }

  function handleMouseMove(event: MapLayerMouseEvent) {
    const next = hoveredFromEvent(event)
    setHovered(next)
    setCursor(next || event.features?.length ? 'pointer' : 'grab')
  }

  function handleClick(event: MapLayerMouseEvent) {
    const checkpoint = hoveredFromEvent(event)
    if (checkpoint) {
      onSelect(checkpoint.route_id)
      return
    }
    const route = event.features?.find((f) => f.layer.id === 'routes-line')
    if (route) onSelect(String(route.properties.id))
  }

  return (
    <Map
      ref={mapRef}
      initialViewState={{ longitude: -96.5, latitude: 39, zoom: 3.4 }}
      mapStyle={MAP_STYLE}
      interactiveLayerIds={['checkpoints', 'routes-line']}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHovered(null)}
      onClick={handleClick}
      onLoad={exposeMapForTests}
      cursor={cursor}
      attributionControl={{ compact: true }}
    >
      <NavigationControl position="top-right" />

      <Source id="routes" type="geojson" data={routes}>
        <Layer id="routes-casing" type="line" layout={lineLayout} paint={routeCasingPaint} />
        <Layer id="routes-line" type="line" layout={lineLayout} paint={routeLinePaint} />
      </Source>

      <Source id="heatmap" type="geojson" data={heatmap}>
        {LEVELS.map((level) => (
          <Layer
            key={level.key}
            id={`heatmap-${level.key}`}
            type="heatmap"
            beforeId="routes-casing"
            layout={{ visibility: showHeatmap ? 'visible' : 'none' }}
            paint={heatmapPaint(level.key, heatmapWeightExpression(heatmapHour, level.value), heatmapRadius)}
          />
        ))}
      </Source>

      <Source id="checkpoints" type="geojson" data={checkpoints}>
        <Layer
          id="checkpoints"
          type="circle"
          layout={{ visibility: showCheckpoints ? 'visible' : 'none' }}
          paint={checkpointPaint}
        />
      </Source>

      {plan && (
        <>
          <Marker longitude={plan.inputs.origin.lon} latitude={plan.inputs.origin.lat} anchor="bottom">
            <div className="pin" title={plan.inputs.origin.name}>
              A
            </div>
          </Marker>
          <Marker longitude={plan.inputs.destination.lon} latitude={plan.inputs.destination.lat} anchor="bottom">
            <div className="pin pin--destination" title={plan.inputs.destination.name}>
              B
            </div>
          </Marker>
        </>
      )}

      {hovered && (
        <Popup
          longitude={hovered.lon}
          latitude={hovered.lat}
          offset={12}
          maxWidth="280px"
          closeButton={false}
          closeOnClick={false}
          className="checkpoint-popup"
        >
          <CheckpointDetails checkpoint={hovered} />
        </Popup>
      )}

      <Legend />
    </Map>
  )
}

function heatmapPaint(
  levelKey: string,
  weight: ExpressionSpecification,
  radius: ExpressionSpecification | number,
): HeatmapLayerSpecification['paint'] {
  return {
    'heatmap-weight': weight,
    'heatmap-color': heatmapColors[levelKey],
    'heatmap-radius': radius,
    'heatmap-intensity': HEATMAP_INTENSITY,
  }
}

function CheckpointDetails({ checkpoint }: { checkpoint: CheckpointProps }) {
  const level = LEVEL_BY_KEY[checkpoint.level]
  return (
    <div className="popup">
      <div className="popup__head">
        <strong>{checkpoint.route_name}</strong> · mile {Math.round(checkpoint.mile)}
      </div>
      <div className="popup__level" style={{ background: level.color }}>
        {level.label}
      </div>
      <dl>
        <dt>ETA</dt>
        <dd>{formatDateTime(checkpoint.eta)}</dd>
        <dt>Wind</dt>
        <dd>
          {Math.round(checkpoint.wind_mph)} mph
          {checkpoint.gust_mph != null ? ` (gusts ${Math.round(checkpoint.gust_mph)})` : ''}
        </dd>
        <dt>Rain</dt>
        <dd>{checkpoint.rain_in_hr.toFixed(2)} in/hr</dd>
        <dt>Snow</dt>
        <dd>{checkpoint.snow_in_hr.toFixed(1)} in/hr</dd>
      </dl>
      <p className="popup__reason">{checkpoint.reason}</p>
    </div>
  )
}

function Legend() {
  return (
    <div className="legend" aria-label="Legend">
      <div className="legend__title">Risk level</div>
      {LEVELS.map((l) => (
        <div key={l.key} className="legend__row">
          <span className="legend__dot" style={{ background: l.color }} />
          {l.label}
        </div>
      ))}
      <div className="legend__row legend__row--lines">
        <span className="legend__line" style={{ background: SELECTED_COLOR }} /> selected route
      </div>
      <div className="legend__row legend__row--lines">
        <span className="legend__line" style={{ background: OTHER_COLOR }} /> other routes
      </div>
      <div className="legend__hint">
        Dots: risk at each checkpoint's ETA (hover for details).
        <br />
        Shading: forecast risk at the slider time.
      </div>
    </div>
  )
}
