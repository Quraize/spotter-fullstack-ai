import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { formatDateTime } from '../lib/format'
import { hours } from '../test/fixtures/plan'
import { HeatmapControls } from './HeatmapControls'

function setup(props: Partial<React.ComponentProps<typeof HeatmapControls>> = {}) {
  const onHourChange = vi.fn()
  const onShowHeatmapChange = vi.fn()
  const onShowCheckpointsChange = vi.fn()
  render(
    <HeatmapControls
      hours={hours}
      hour={0}
      showHeatmap
      showCheckpoints
      onHourChange={onHourChange}
      onShowHeatmapChange={onShowHeatmapChange}
      onShowCheckpointsChange={onShowCheckpointsChange}
      {...props}
    />,
  )
  return { onHourChange, onShowHeatmapChange, onShowCheckpointsChange }
}

describe('HeatmapControls', () => {
  it('renders a 0-48 hour slider labelled with the absolute forecast time', () => {
    setup({ hour: 6 })
    const slider = screen.getByRole('slider', { name: /forecast hour/i })
    expect(slider).toHaveAttribute('min', '0')
    expect(slider).toHaveAttribute('max', '48')
    expect(slider).toHaveAttribute('step', '1')
    expect(slider).toHaveValue('6')
    expect(slider).toHaveAttribute('aria-valuetext', `${formatDateTime(hours[6])} (+6 h)`)
    expect(screen.getByText(formatDateTime(hours[6]))).toBeInTheDocument()
    expect(screen.getByText(/\+6 h after departure/i)).toBeInTheDocument()
  })

  it('says "departure" at hour 0', () => {
    setup({ hour: 0 })
    expect(screen.getByText(/at departure/i)).toBeInTheDocument()
    expect(screen.getByRole('slider', { name: /forecast hour/i })).toHaveAttribute(
      'aria-valuetext',
      `${formatDateTime(hours[0])} (departure)`,
    )
  })

  it('reports slider changes as integers', () => {
    const { onHourChange } = setup()
    fireEvent.change(screen.getByRole('slider', { name: /forecast hour/i }), { target: { value: '17' } })
    expect(onHourChange).toHaveBeenCalledWith(17)
  })

  it('toggles the heatmap and checkpoint layers', async () => {
    const { onShowHeatmapChange, onShowCheckpointsChange } = setup()
    const user = userEvent.setup()
    await user.click(screen.getByRole('checkbox', { name: /heatmap/i }))
    expect(onShowHeatmapChange).toHaveBeenCalledWith(false)
    await user.click(screen.getByRole('checkbox', { name: /checkpoints/i }))
    expect(onShowCheckpointsChange).toHaveBeenCalledWith(false)
  })

  it('disables the slider when the heatmap is hidden', () => {
    setup({ showHeatmap: false })
    expect(screen.getByRole('slider', { name: /forecast hour/i })).toBeDisabled()
  })

  it('clamps the hour to the available window', () => {
    setup({ hour: 99 })
    expect(screen.getByRole('slider', { name: /forecast hour/i })).toHaveValue('48')
  })
})
