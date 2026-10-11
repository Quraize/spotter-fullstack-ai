import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { Legend } from './Legend'

describe('Legend', () => {
  it('lists the five risk levels and the two route line styles', () => {
    render(<Legend />)
    for (const label of ['Low', 'Moderate', 'High', 'Severe', 'No Travel']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.getByText(/selected route/i)).toBeInTheDocument()
    expect(screen.getByText(/other routes/i)).toBeInTheDocument()
  })

  it('collapses to a small "Legend" button and expands again', async () => {
    const user = userEvent.setup()
    render(<Legend />)
    const hide = screen.getByRole('button', { name: /hide legend/i })
    expect(hide).toHaveAttribute('aria-expanded', 'true')

    await user.click(hide)
    expect(screen.queryByText('Moderate')).toBeNull()
    const show = screen.getByRole('button', { name: /show legend/i })
    expect(show).toHaveAttribute('aria-expanded', 'false')

    await user.click(show)
    expect(screen.getByText('Moderate')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /hide legend/i })).toBeInTheDocument()
  })
})
