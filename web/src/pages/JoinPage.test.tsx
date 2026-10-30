import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readCredentials, useSessionStore } from '../store/sessionStore'
import { mockApi } from '../test/mockApi'
import { JoinPage } from './JoinPage'

beforeEach(() => {
  window.localStorage.clear()
  useSessionStore.setState({ team: null, facilitator: null })
  window.history.replaceState(null, '', '/join')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function fill(code: string, name: string) {
  fireEvent.change(screen.getByLabelText('Session code'), { target: { value: code } })
  fireEvent.change(screen.getByLabelText(/Team name/), { target: { value: name } })
  fireEvent.click(screen.getByRole('button', { name: 'Join' }))
}

describe('JoinPage', () => {
  it('joins, stores the token and opens /team', async () => {
    const fetchMock = mockApi({
      'POST /api/sessions/ABC234/teams': { status: 201, body: { teamId: 't1', teamName: 'Red Team', token: 'tok' } },
    })
    render(<JoinPage />)
    fill('abc234', '  Red Team ')
    await waitFor(() => expect(window.location.pathname).toBe('/team'))
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/sessions/ABC234/teams',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ teamName: 'Red Team' }) }),
    )
    const team = { sessionCode: 'ABC234', teamId: 't1', teamName: 'Red Team', token: 'tok' }
    expect(useSessionStore.getState().team).toEqual(team)
    expect(readCredentials().team).toEqual(team)
  })

  it.each([
    [404, /no session with code ABC234/],
    [409, /session is full/],
    [503, /not set up/],
  ])('explains a %i', async (status, message) => {
    mockApi({ 'POST /api/sessions/ABC234/teams': { status, body: { detail: 'x' } } })
    render(<JoinPage />)
    fill('ABC234', 'Red')
    expect((await screen.findByRole('alert')).textContent).toMatch(message)
    expect(window.location.pathname).toBe('/join')
    expect(useSessionStore.getState().team).toBeNull()
  })

  it('needs a code and a name', () => {
    render(<JoinPage />)
    const join = screen.getByRole('button', { name: 'Join' }) as HTMLButtonElement
    expect(join.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Session code'), { target: { value: 'ABC234' } })
    fireEvent.change(screen.getByLabelText(/Team name/), { target: { value: '   ' } })
    expect(join.disabled).toBe(true)
  })

  it('prefills the code from ?code=', () => {
    window.history.replaceState(null, '', '/join?code=abc234')
    render(<JoinPage />)
    expect((screen.getByLabelText('Session code') as HTMLInputElement).value).toBe('ABC234')
  })
})
