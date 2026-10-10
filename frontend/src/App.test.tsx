import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { ApiError } from './api/client'
import { planFixture, planWith } from './test/fixtures/plan'

vi.mock('./components/MapView', () => ({
  MapView: (props: { selectedId: string | null }) => <div data-testid="map" data-selected={props.selectedId ?? ''} />,
}))

vi.mock('./api/client', async () => {
  const actual = await vi.importActual<typeof import('./api/client')>('./api/client')
  return { ...actual, postPlan: vi.fn() }
})

import { postPlan } from './api/client'

const postPlanMock = vi.mocked(postPlan)

beforeEach(() => {
  postPlanMock.mockReset()
})

describe('App', () => {
  it('shows the form and the map before any plan', () => {
    render(<App />)
    expect(screen.getByLabelText(/origin/i)).toBeInTheDocument()
    expect(screen.getByTestId('map')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /route \d/i })).toBeNull()
  })

  it('plans a trip and selects the recommended route', async () => {
    postPlanMock.mockResolvedValue(planFixture)
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: /plan routes/i }))

    expect(await screen.findAllByRole('button', { name: /route \d/i })).toHaveLength(3)
    expect(screen.getByTestId('map')).toHaveAttribute('data-selected', 'r2')
    expect(postPlanMock).toHaveBeenCalledTimes(1)
    expect(postPlanMock.mock.calls[0][0]).toMatchObject({ origin: 'Chicago, IL', destination: 'Denver, CO' })
  })

  it('lets a card change the selected route', async () => {
    postPlanMock.mockResolvedValue(planFixture)
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    const cards = await screen.findAllByRole('button', { name: /route \d/i })
    await user.click(cards[1])
    expect(screen.getByTestId('map')).toHaveAttribute('data-selected', 'r1')
  })

  it('shows API errors', async () => {
    postPlanMock.mockRejectedValue(new ApiError(422, 'geocode_not_found', "No location found for 'Atlantis'"))
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent("No location found for 'Atlantis'")
  })

  it('shows planner warnings', async () => {
    postPlanMock.mockResolvedValue(planWith({ warnings: ['The routing provider returned only 2 distinct routes for this trip.'] }))
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    await waitFor(() => expect(screen.getByText(/only 2 distinct routes/i)).toBeInTheDocument())
  })
})
