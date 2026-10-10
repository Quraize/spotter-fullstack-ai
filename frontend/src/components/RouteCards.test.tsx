import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { planFixture, planWith } from '../test/fixtures/plan'
import { RouteCards } from './RouteCards'

function setup(plan = planFixture, selectedId: string | null = 'r2') {
  const onSelect = vi.fn()
  render(<RouteCards plan={plan} selectedId={selectedId} onSelect={onSelect} />)
  return { onSelect, user: userEvent.setup() }
}

describe('RouteCards', () => {
  it('shows the places the origin and destination resolved to', () => {
    render(<RouteCards plan={planFixture} selectedId={null} onSelect={() => {}} />)
    expect(screen.getByText(/from/i).closest('p')).toHaveTextContent('From Chicago, IL to Denver, CO')
  })

  it('lists routes in recommendation order with their summaries', () => {
    setup()
    const cards = screen.getAllByRole('button', { name: /route \d/i })
    expect(cards.map((c) => within(c).getByRole('heading').textContent)).toEqual(['Route 2', 'Route 1', 'Route 3'])

    const first = cards[0]
    expect(within(first).getByText('1,143 mi')).toBeInTheDocument()
    expect(within(first).getByText('15h 44m')).toBeInTheDocument()
    expect(within(first).getByText(/arrive/i)).toBeInTheDocument()
    expect(within(first).getByText('Recommended')).toBeInTheDocument()
  })

  it('shows the risk mix as a bar with a segment per level that has miles', () => {
    setup()
    const cards = screen.getAllByRole('button', { name: /route \d/i })
    const routeOne = cards[1]
    expect(within(routeOne).getByTitle('Moderate: 100 mi')).toBeInTheDocument()
    expect(within(routeOne).getByTitle('Low: 908 mi')).toBeInTheDocument()
    expect(within(routeOne).queryByTitle(/Severe/)).toBeNull()
  })

  it('badges routes with No Travel conditions', () => {
    setup()
    const cards = screen.getAllByRole('button', { name: /route \d/i })
    expect(within(cards[2]).getByText('Travel not advised')).toBeInTheDocument()
    expect(within(cards[0]).queryByText('Travel not advised')).toBeNull()
  })

  it('marks the selected card and reports clicks', async () => {
    const { onSelect, user } = setup()
    const cards = screen.getAllByRole('button', { name: /route \d/i })
    expect(cards[0]).toHaveAttribute('aria-pressed', 'true')
    expect(cards[1]).toHaveAttribute('aria-pressed', 'false')
    await user.click(cards[1])
    expect(onSelect).toHaveBeenCalledWith('r1')
  })

  it('explains the recommendation', () => {
    setup()
    expect(screen.getByText(/lowest average risk/i)).toBeInTheDocument()
  })

  it('says so when no route can be recommended', () => {
    const plan = planWith({
      recommended_route_id: null,
      recommendation: {
        route_id: null,
        ranked_ids: ['r2', 'r1', 'r3'],
        reason: 'All routes cross No Travel conditions, so none is recommended.',
        all_no_travel: true,
      },
    })
    setup(plan, null)
    expect(screen.getByRole('status')).toHaveTextContent(/no route is recommended/i)
    expect(screen.queryByText('Recommended')).toBeNull()
  })
})
