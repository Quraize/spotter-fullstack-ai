import type { ReactNode } from 'react'

type Direction = 'left' | 'right' | 'up' | 'down'

const ROTATION: Record<Direction, number> = { right: 0, down: 90, left: 180, up: 270 }

interface Props {
  /** Accessible name, e.g. "Hide panel"; also the tooltip. */
  label: string
  expanded: boolean
  /** Which way the chevron points. */
  direction: Direction
  onClick: () => void
  /** Optional visible text next to the chevron (renders as a pill). */
  children?: ReactNode
}

/** Small chevron button that folds a panel away or brings it back. */
export function PanelToggle({ label, expanded, direction, onClick, children }: Props) {
  return (
    <button
      type="button"
      className={children ? 'panel-toggle panel-toggle--pill' : 'panel-toggle'}
      aria-label={label}
      title={label}
      aria-expanded={expanded}
      onClick={onClick}
    >
      {children}
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" style={{ transform: `rotate(${ROTATION[direction]}deg)` }}>
        <path d="M6 3l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  )
}
