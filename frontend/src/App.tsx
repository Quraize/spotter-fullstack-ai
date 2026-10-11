import { useState } from 'react'

import './App.css'
import { ApiError, apiErrorMessage, postPlan } from './api/client'
import type { Plan, PlanRequest } from './api/types'
import { HeatmapControls } from './components/HeatmapControls'
import { MapView } from './components/MapView'
import { PanelToggle } from './components/PanelToggle'
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
  // The side panel folds into a thin rail so the map can use the width; its contents stay mounted.
  const [panelOpen, setPanelOpen] = useState(true)
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
      setError(e instanceof ApiError ? apiErrorMessage(e) : 'Something went wrong while planning. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={panelOpen ? 'app' : 'app app--panel-collapsed'}>
      {!panelOpen && (
        <div className="rail">
          <PanelToggle label="Show panel" expanded={false} direction="right" onClick={() => setPanelOpen(true)} />
        </div>
      )}
      <aside className="sidebar" hidden={!panelOpen}>
        <header className="sidebar__header">
          <div>
            <h1>Weather-Aware Truck Routing</h1>
            <p className="tagline">Three truck routes, weather sampled at every checkpoint, ranked by the risk rules.</p>
          </div>
          <PanelToggle label="Hide panel" expanded direction="left" onClick={() => setPanelOpen(false)} />
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
