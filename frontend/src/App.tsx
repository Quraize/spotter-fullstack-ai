import { useState } from 'react'

import './App.css'
import { ApiError, postPlan } from './api/client'
import type { Plan, PlanRequest } from './api/types'
import { HeatmapControls } from './components/HeatmapControls'
import { MapView } from './components/MapView'
import { PlanForm } from './components/PlanForm'
import { RouteCards } from './components/RouteCards'
import { useFrameThrottledValue } from './hooks/useFrameThrottledValue'

const INITIAL_FORM = { origin: 'Chicago, IL', destination: 'Denver, CO', loadWeightLb: 42000, intervalMiles: 25 as const }

export default function App() {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hour, setHour] = useState(0)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const [showCheckpoints, setShowCheckpoints] = useState(true)
  // The slider label follows every input event; the map re-styles once per frame.
  const mapHour = useFrameThrottledValue(hour)

  async function handleSubmit(request: PlanRequest) {
    setLoading(true)
    setError(null)
    try {
      const next = await postPlan(request)
      setPlan(next)
      setSelectedId(next.recommended_route_id ?? next.recommendation.ranked_ids[0] ?? null)
      setHour(0)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong while planning. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <header className="sidebar__header">
          <h1>Weather-Aware Truck Routing</h1>
          <p className="tagline">Three truck routes, weather sampled at every checkpoint, ranked by the risk rules.</p>
        </header>
        <PlanForm initial={INITIAL_FORM} loading={loading} onSubmit={handleSubmit} />
        {error && (
          <div role="alert" className="notice notice--error">
            {error}
          </div>
        )}
        {plan?.warnings.map((warning) => (
          <div key={warning} className="notice notice--warning">
            {warning}
          </div>
        ))}
        {plan && <RouteCards plan={plan} selectedId={selectedId} onSelect={setSelectedId} />}
      </aside>
      <main className="map-area">
        <MapView
          plan={plan}
          selectedId={selectedId}
          onSelect={setSelectedId}
          hour={mapHour}
          showHeatmap={showHeatmap}
          showCheckpoints={showCheckpoints}
        />
        {plan && (
          <HeatmapControls
            hours={plan.heatmap.hours}
            hour={hour}
            showHeatmap={showHeatmap}
            showCheckpoints={showCheckpoints}
            onHourChange={setHour}
            onShowHeatmapChange={setShowHeatmap}
            onShowCheckpointsChange={setShowCheckpoints}
          />
        )}
      </main>
    </div>
  )
}
