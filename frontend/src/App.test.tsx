import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { ApiError } from './api/client'
import { planFixture, planWith } from './test/fixtures/plan'

vi.mock('./components/MapView', () => ({
  MapView: (props: { selectedId: string | null; hour: number; showHeatmap: boolean; showCheckpoints: boolean }) => (
    <div
      data-testid="map"
      data-selected={props.selectedId ?? ''}
      data-hour={props.hour}
      data-heatmap={String(props.showHeatmap)}
      data-checkpoints={String(props.showCheckpoints)}
    />
  ),
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

  it('shows the heatmap controls only once a plan exists', async () => {
    postPlanMock.mockResolvedValue(planFixture)
    const user = userEvent.setup()
    render(<App />)
    expect(screen.queryByRole('slider', { name: /forecast hour/i })).toBeNull()
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    expect(await screen.findByRole('slider', { name: /forecast hour/i })).toHaveValue('0')
    expect(screen.getByTestId('map')).toHaveAttribute('data-hour', '0')
    expect(screen.getByTestId('map')).toHaveAttribute('data-heatmap', 'true')
    expect(screen.getByTestId('map')).toHaveAttribute('data-checkpoints', 'true')
  })

  it('passes the slider hour to the map, throttled to animation frames', async () => {
    postPlanMock.mockResolvedValue(planFixture)
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    const slider = await screen.findByRole('slider', { name: /forecast hour/i })
    fireEvent.change(slider, { target: { value: '12' } })
    expect(slider).toHaveValue('12')
    await waitFor(() => expect(screen.getByTestId('map')).toHaveAttribute('data-hour', '12'))
  })

  it('resets the slider to departure for a new plan', async () => {
    postPlanMock.mockResolvedValue(planFixture)
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    const slider = await screen.findByRole('slider', { name: /forecast hour/i })
    fireEvent.change(slider, { target: { value: '30' } })
    await waitFor(() => expect(screen.getByTestId('map')).toHaveAttribute('data-hour', '30'))
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    await waitFor(() => expect(screen.getByRole('slider', { name: /forecast hour/i })).toHaveValue('0'))
  })

  it('lets the driver hide the heatmap or the checkpoints', async () => {
    postPlanMock.mockResolvedValue(planFixture)
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    await screen.findByRole('slider', { name: /forecast hour/i })
    await user.click(screen.getByRole('checkbox', { name: /heatmap/i }))
    expect(screen.getByTestId('map')).toHaveAttribute('data-heatmap', 'false')
    await user.click(screen.getByRole('checkbox', { name: /checkpoints/i }))
    expect(screen.getByTestId('map')).toHaveAttribute('data-checkpoints', 'false')
  })
})
