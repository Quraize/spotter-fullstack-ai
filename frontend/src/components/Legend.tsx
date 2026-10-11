import { useState } from 'react'

import { OTHER_ROUTE_COLOR, SELECTED_ROUTE_COLOR } from '../lib/mapStyle'
import { LEVELS } from '../lib/risk'
import { PanelToggle } from './PanelToggle'

/** Map legend: risk colours and route line styles. Folds down to a "Legend" pill to free the map. */
export function Legend() {
  const [open, setOpen] = useState(true)

  if (!open) {
    return (
      <div className="legend legend--collapsed" aria-label="Legend">
        <PanelToggle label="Show legend" expanded={false} direction="up" onClick={() => setOpen(true)}>
          Legend
        </PanelToggle>
      </div>
    )
  }

  return (
    <div className="legend" aria-label="Legend">
      <div className="legend__head">
        <span className="legend__title">Risk level</span>
        <PanelToggle label="Hide legend" expanded direction="down" onClick={() => setOpen(false)} />
      </div>
      {LEVELS.map((l) => (
        <div key={l.key} className="legend__row">
          <span className="legend__dot" style={{ background: l.color }} />
          {l.label}
        </div>
      ))}
      <div className="legend__row legend__row--lines">
        <span className="legend__line" style={{ background: SELECTED_ROUTE_COLOR }} /> selected route
      </div>
      <div className="legend__row legend__row--lines">
        <span className="legend__line" style={{ background: OTHER_ROUTE_COLOR }} /> other routes
      </div>
      <div className="legend__hint">
        Dots: risk at each checkpoint's ETA (hover for details).
        <br />
        Shading: forecast risk at the slider time.
      </div>
    </div>
  )
}
