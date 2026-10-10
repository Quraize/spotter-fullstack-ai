import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { toIsoWithOffset } from '../lib/format'
import { PlanForm } from './PlanForm'

const initial = {
  origin: 'Chicago, IL',
  destination: 'Denver, CO',
  departureLocal: '2026-10-11T08:00',
  loadWeightLb: 42000,
  intervalMiles: 25 as const,
}

function setup(props: Partial<React.ComponentProps<typeof PlanForm>> = {}) {
  const onSubmit = vi.fn()
  const user = userEvent.setup()
  render(<PlanForm initial={initial} loading={false} onSubmit={onSubmit} {...props} />)
  return { onSubmit, user }
}

describe('PlanForm', () => {
  it('renders every input the PDF asks for', () => {
    setup()
    expect(screen.getByLabelText(/origin/i)).toHaveValue('Chicago, IL')
    expect(screen.getByLabelText(/destination/i)).toHaveValue('Denver, CO')
    expect(screen.getByLabelText(/departure/i)).toHaveValue('2026-10-11T08:00')
    expect(screen.getByLabelText(/load weight/i)).toHaveValue(42000)
    expect(screen.getByRole('radio', { name: '10 mi' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: '25 mi' })).toBeChecked()
    expect(screen.getByRole('radio', { name: '50 mi' })).not.toBeChecked()
  })

  it('submits a typed request with the departure converted to ISO 8601 with offset', async () => {
    const { onSubmit, user } = setup()
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    expect(onSubmit).toHaveBeenCalledWith({
      origin: 'Chicago, IL',
      destination: 'Denver, CO',
      departure_time: toIsoWithOffset('2026-10-11T08:00'),
      load_weight_lb: 42000,
      sample_interval_miles: 25,
    })
  })

  it('lets the driver pick the sampling interval', async () => {
    const { onSubmit, user } = setup()
    await user.click(screen.getByRole('radio', { name: '50 mi' }))
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    expect(onSubmit.mock.calls[0][0].sample_interval_miles).toBe(50)
  })

  it('refuses to submit without an origin', async () => {
    const { onSubmit, user } = setup()
    await user.clear(screen.getByLabelText(/origin/i))
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText(/enter an origin/i)).toBeInTheDocument()
  })

  it('refuses a non-positive load weight', async () => {
    const { onSubmit, user } = setup()
    const load = screen.getByLabelText(/load weight/i)
    await user.clear(load)
    await user.type(load, '0')
    await user.click(screen.getByRole('button', { name: /plan routes/i }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText(/load weight must be greater than 0/i)).toBeInTheDocument()
  })

  it('disables the button while a plan is loading', () => {
    setup({ loading: true })
    const button = screen.getByRole('button', { name: /planning/i })
    expect(button).toBeDisabled()
  })
})
