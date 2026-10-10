import { useState, type FormEvent } from 'react'

import type { PlanRequest, SampleInterval } from '../api/types'
import { defaultDepartureLocal, toIsoWithOffset } from '../lib/format'

export interface FormValues {
  origin: string
  destination: string
  departureLocal: string
  loadWeightLb: number
  intervalMiles: SampleInterval
}

interface Props {
  initial?: Partial<FormValues>
  loading: boolean
  onSubmit: (request: PlanRequest) => void
}

const INTERVALS: SampleInterval[] = [10, 25, 50]

type Errors = Partial<Record<keyof FormValues, string>>

export function PlanForm({ initial, loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState(initial?.origin ?? '')
  const [destination, setDestination] = useState(initial?.destination ?? '')
  const [departureLocal, setDepartureLocal] = useState(initial?.departureLocal ?? defaultDepartureLocal())
  const [loadWeight, setLoadWeight] = useState(String(initial?.loadWeightLb ?? 40000))
  const [interval, setInterval] = useState<SampleInterval>(initial?.intervalMiles ?? 25)
  const [errors, setErrors] = useState<Errors>({})

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const next: Errors = {}
    if (!origin.trim()) next.origin = 'Enter an origin.'
    if (!destination.trim()) next.destination = 'Enter a destination.'
    let departureIso = ''
    try {
      departureIso = toIsoWithOffset(departureLocal)
    } catch {
      next.departureLocal = 'Enter a departure date and time.'
    }
    const load = Number(loadWeight)
    if (!(load > 0)) next.loadWeightLb = 'Load weight must be greater than 0.'
    setErrors(next)
    if (Object.keys(next).length > 0) return
    onSubmit({
      origin: origin.trim(),
      destination: destination.trim(),
      departure_time: departureIso,
      load_weight_lb: load,
      sample_interval_miles: interval,
    })
  }

  return (
    <form className="plan-form" onSubmit={handleSubmit} noValidate>
      <div className="field">
        <label htmlFor="origin">Origin</label>
        <input
          id="origin"
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
          placeholder="City, state or address"
          autoComplete="off"
        />
        {errors.origin && <p className="field-error">{errors.origin}</p>}
      </div>

      <div className="field">
        <label htmlFor="destination">Destination</label>
        <input
          id="destination"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="City, state or address"
          autoComplete="off"
        />
        {errors.destination && <p className="field-error">{errors.destination}</p>}
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor="departure">Departure date &amp; time</label>
          <input
            id="departure"
            type="datetime-local"
            value={departureLocal}
            onChange={(e) => setDepartureLocal(e.target.value)}
            step={60}
          />
          {errors.departureLocal && <p className="field-error">{errors.departureLocal}</p>}
        </div>

        <div className="field">
          <label htmlFor="load">Load weight (lb)</label>
          <input
            id="load"
            type="number"
            inputMode="numeric"
            min={1}
            step={1000}
            value={loadWeight}
            onChange={(e) => setLoadWeight(e.target.value)}
          />
          {errors.loadWeightLb && <p className="field-error">{errors.loadWeightLb}</p>}
        </div>
      </div>

      <fieldset className="field">
        <legend>Sample weather every</legend>
        <div className="radio-row">
          {INTERVALS.map((miles) => (
            <label key={miles} className={`radio ${interval === miles ? 'radio--on' : ''}`}>
              <input
                type="radio"
                name="interval"
                value={miles}
                checked={interval === miles}
                onChange={() => setInterval(miles)}
              />
              {miles} mi
            </label>
          ))}
        </div>
      </fieldset>

      <button type="submit" className="primary" disabled={loading}>
        {loading ? 'Planning…' : 'Plan routes'}
      </button>
    </form>
  )
}
