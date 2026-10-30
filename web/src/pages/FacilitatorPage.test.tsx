import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from '../store/sessionStore'
import { authHeader, mockApi } from '../test/mockApi'
import type { SessionDetail } from '../types'
import { FacilitatorPage } from './FacilitatorPage'

const teams = [
  { teamId: 't1', name: 'Red', joinedAt: '2026-10-26T09:00:00Z', graphVersion: 3, locked: false },
  { teamId: 't2', name: 'Blue', joinedAt: '2026-10-26T09:01:00Z', graphVersion: 0, locked: false },
]

function detail(locked: boolean): SessionDetail {
  return { sessionCode: 'ABC234', createdAt: '2026-10-26T08:59:00Z', teams: teams.map((t) => ({ ...t, locked })) }
}

beforeEach(() => {
  window.localStorage.clear()
  useSessionStore.setState({ team: null, facilitator: null })
  window.history.replaceState(null, '', '/facilitator')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('FacilitatorPage', () => {
  it('creates a session, shows its code and lists the teams', async () => {
    const fetchMock = mockApi({
      'POST /api/sessions': { status: 201, body: { sessionCode: 'ABC234', facilitatorToken: 'fac' } },
      'GET /api/sessions/ABC234': { body: detail(false) },
    })
    render(<FacilitatorPage />)
    fireEvent.change(screen.getByLabelText('Facilitator code'), { target: { value: 'open-sesame' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create session' }))

    expect((await screen.findByLabelText('Session code')).textContent).toBe('ABC234')
    expect(useSessionStore.getState().facilitator).toEqual({ sessionCode: 'ABC234', token: 'fac' })
    const rows = await screen.findAllByRole('row')
    expect(rows.slice(1).map((r) => within(r).getAllByRole('cell')[0].textContent)).toEqual(['Red', 'Blue'])
    const [, sessionCall] = fetchMock.mock.calls
    expect(authHeader(sessionCall[1])).toBe('Bearer fac')
  })

  it('explains a wrong facilitator code', async () => {
    mockApi({ 'POST /api/sessions': { status: 401, body: { detail: 'wrong facilitator code' } } })
    render(<FacilitatorPage />)
    fireEvent.change(screen.getByLabelText('Facilitator code'), { target: { value: 'nope' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create session' }))
    expect((await screen.findByRole('alert')).textContent).toMatch(/Wrong facilitator code/)
  })

  it('locks and unlocks every graph', async () => {
    useSessionStore.setState({ facilitator: { sessionCode: 'ABC234', token: 'fac' } })
    const fetchMock = mockApi({
      'GET /api/sessions/ABC234': { body: detail(false) },
      'POST /api/sessions/ABC234/lock': (init) => ({ body: detail(JSON.parse(String(init.body)).locked) }),
    })
    render(<FacilitatorPage />)
    fireEvent.click(await screen.findByRole('button', { name: /Pencils down/ }))
    await screen.findByRole('button', { name: 'Unlock graphs' })
    expect(screen.getAllByText('Locked')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Unlock graphs' }))
    await screen.findByRole('button', { name: /Pencils down/ })
    const lockBodies = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/lock')).map(([, i]) => i?.body)
    expect(lockBodies).toEqual(['{"locked":true}', '{"locked":false}'])
  })

  it('refreshes the team list on a timer', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      useSessionStore.setState({ facilitator: { sessionCode: 'ABC234', token: 'fac' } })
      const fetchMock = mockApi({ 'GET /api/sessions/ABC234': { body: detail(false) } })
      render(<FacilitatorPage />)
      await screen.findAllByRole('row')
      const before = fetchMock.mock.calls.length
      await vi.advanceTimersByTimeAsync(5000)
      expect(fetchMock.mock.calls.length).toBe(before + 1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('a revoked facilitator token goes back to the create form', async () => {
    useSessionStore.setState({ facilitator: { sessionCode: 'ABC234', token: 'old' } })
    mockApi({ 'GET /api/sessions/ABC234': { status: 401 } })
    render(<FacilitatorPage />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create session' })).toBeTruthy())
    expect(useSessionStore.getState().facilitator).toBeNull()
  })
})
