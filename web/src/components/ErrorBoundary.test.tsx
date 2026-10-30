import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from './ErrorBoundary'

let explode = true
function Fragile() {
  if (explode) throw new Error('boom')
  return <p>fine</p>
}

afterEach(cleanup)

describe('ErrorBoundary', () => {
  it('contains a crash to its panel and can retry', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <div>
        <p>outside</p>
        <ErrorBoundary name="the run bar">
          <Fragile />
        </ErrorBoundary>
      </div>,
    )
    expect(screen.getByText('outside')).toBeTruthy() // the rest of the page survives
    expect(screen.getByRole('alert').textContent).toContain('Something went wrong in the run bar.')
    explode = false
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(screen.getByText('fine')).toBeTruthy()
    vi.restoreAllMocks()
  })
})
