import type { Plan, Route, RouteSummary } from '../api/types'
import { formatDateTime, formatDuration, formatMiles, formatRisk } from '../lib/format'
import { LEVELS, LEVEL_BY_KEY } from '../lib/risk'

interface Props {
  plan: Plan
  selectedId: string | null
  onSelect: (id: string) => void
}

export function RouteCards({ plan, selectedId, onSelect }: Props) {
  const byId = new Map(plan.routes.map((r) => [r.id, r]))
  const ordered = plan.recommendation.ranked_ids.map((id) => byId.get(id)).filter((r): r is Route => r !== undefined)
  const recommended = plan.recommended_route_id ? byId.get(plan.recommended_route_id) : undefined

  return (
    <section className="results" aria-label="Route options">
      <p className="results__places">
        From <strong>{plan.inputs.origin.name}</strong> to <strong>{plan.inputs.destination.name}</strong>
      </p>
      <div role="status" className={`recommendation ${recommended ? '' : 'recommendation--none'}`}>
        <strong>{recommended ? `Recommended: ${recommended.name}` : 'No route is recommended.'}</strong>
        <span>{plan.recommendation.reason}</span>
      </div>
      <ul className="route-list">
        {ordered.map((route) => (
          <li key={route.id}>
            <RouteCard
              route={route}
              recommended={route.id === plan.recommended_route_id}
              selected={route.id === selectedId}
              onSelect={onSelect}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}

interface CardProps {
  route: Route
  recommended: boolean
  selected: boolean
  onSelect: (id: string) => void
}

function RouteCard({ route, recommended, selected, onSelect }: CardProps) {
  const worst = LEVEL_BY_KEY[route.summary.worst_level]
  const worstCheckpoint = route.checkpoints[route.summary.worst_checkpoint_index]
  return (
    <button
      type="button"
      className={`route-card ${selected ? 'route-card--selected' : ''}`}
      aria-pressed={selected}
      onClick={() => onSelect(route.id)}
    >
      <div className="route-card__head">
        <h3>{route.name}</h3>
        <span className="route-card__rank">#{route.rank}</span>
        {recommended && <span className="badge badge--good">Recommended</span>}
        {route.summary.no_travel && <span className="badge badge--bad">Travel not advised</span>}
      </div>
      <dl className="route-card__stats">
        <div>
          <dt>Distance</dt>
          <dd>{formatMiles(route.distance_miles)}</dd>
        </div>
        <div>
          <dt>Drive time</dt>
          <dd>{formatDuration(route.duration_seconds)}</dd>
        </div>
        <div>
          <dt>Arrive</dt>
          <dd>{formatDateTime(route.arrival_time)}</dd>
        </div>
      </dl>
      <RiskBar summary={route.summary} />
      <p className="route-card__risk">
        Avg risk {formatRisk(route.summary.average_risk)} · worst {worst.label}
        {worstCheckpoint && worst.value > 0 ? ` at mile ${Math.round(worstCheckpoint.mile)}` : ''}
      </p>
    </button>
  )
}

function RiskBar({ summary }: { summary: RouteSummary }) {
  const total = summary.total_miles || 1
  return (
    <div className="risk-bar" aria-hidden="false">
      {LEVELS.filter((l) => summary.miles_by_level[l.key] > 0).map((l) => {
        const miles = summary.miles_by_level[l.key]
        return (
          <span
            key={l.key}
            className="risk-bar__segment"
            title={`${l.label}: ${formatMiles(miles)}`}
            style={{ width: `${(100 * miles) / total}%`, background: l.color }}
          />
        )
      })}
    </div>
  )
}
