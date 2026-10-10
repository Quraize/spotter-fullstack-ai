import { formatDateTime } from '../lib/format'
import { clampHour } from '../lib/heatmap'

interface Props {
  hours: string[] // ISO timestamps, index 0 = departure
  hour: number
  showHeatmap: boolean
  showCheckpoints: boolean
  onHourChange: (hour: number) => void
  onShowHeatmapChange: (show: boolean) => void
  onShowCheckpointsChange: (show: boolean) => void
}

export function HeatmapControls({
  hours,
  hour,
  showHeatmap,
  showCheckpoints,
  onHourChange,
  onShowHeatmapChange,
  onShowCheckpointsChange,
}: Props) {
  const maxHour = Math.max(0, hours.length - 1)
  const current = clampHour(hour, maxHour)
  const when = formatDateTime(hours[current])
  const offset = current === 0 ? 'departure' : `+${current} h`

  return (
    <div className="heatmap-controls" role="group" aria-label="Weather heatmap">
      <div className="heatmap-controls__row">
        <div className="heatmap-controls__label">
          Forecast risk at <strong>{when}</strong>{' '}
          <span className="heatmap-controls__offset">{current === 0 ? '(at departure)' : `(${offset} after departure)`}</span>
        </div>
        <div className="heatmap-controls__toggles">
          <label className="toggle">
            <input type="checkbox" checked={showHeatmap} onChange={(e) => onShowHeatmapChange(e.target.checked)} />
            Heatmap
          </label>
          <label className="toggle">
            <input type="checkbox" checked={showCheckpoints} onChange={(e) => onShowCheckpointsChange(e.target.checked)} />
            Checkpoints
          </label>
        </div>
      </div>
      <input
        className="heatmap-controls__slider"
        type="range"
        aria-label="Forecast hour"
        aria-valuetext={`${when} (${offset})`}
        min={0}
        max={maxHour}
        step={1}
        value={current}
        disabled={!showHeatmap}
        onChange={(e) => onHourChange(clampHour(Number(e.target.value), maxHour))}
      />
      <div className="heatmap-controls__ticks" aria-hidden="true">
        <span>Departure</span>
        <span>+{Math.round(maxHour / 2)} h</span>
        <span>+{maxHour} h</span>
      </div>
    </div>
  )
}
