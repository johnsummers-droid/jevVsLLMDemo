// T24: the facilitator's official run controls, the per-team run column and leaderboard, and /screen.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionLiveStore } from '../store/sessionLiveStore'
import { useSessionStore } from '../store/sessionStore'
import { FakeWebSocket } from '../test/fakeSocket'
import { mockApi } from '../test/mockApi'
import type { LeaderboardRow, RunMetrics, SessionDetail } from '../types'
import { FacilitatorPage } from './FacilitatorPage'
import { ScreenPage } from './ScreenPage'

const detail: SessionDetail = {
  sessionCode: 'ABC234',
  createdAt: '2026-10-30T09:00:00Z',
  locked: false,
  teams: [
    { teamId: 'red', name: 'Red', joinedAt: '2026-10-30T09:01:00Z', graphVersion: 4, locked: false },
    { teamId: 'blue', name: 'Blue', joinedAt: '2026-10-30T09:02:00Z', graphVersion: 2, locked: false },
  ],
}
const metrics: RunMetrics = {
  total: 30, completed: 30, automationRate: 0.7, escalationRate: 0.2, unsafeReleaseRate: 0, droppedRate: 0,
  p50LatencyMs: 300, p95LatencyMs: 650, costPer1KUsd: 900, decisionQuality: 0.9, score: 77,
}
const board: LeaderboardRow[] = [
  { teamId: 'red', teamName: 'Red', runId: 'r1', status: 'completed', rank: 1, metrics },
  { teamId: 'blue', teamName: 'Blue', runId: 'b1', status: 'running', rank: 2 },
]
const started = (teamId: string, runId: string) => ({
  type: 'run_started', runId, teamId, seq: 0, simMs: 0, config: { mode: 'official', packId: 'official', seed: 7 },
})

function goLive() {
  const ws = FakeWebSocket.latest()
  act(() => {
    ws.open()
    ws.receive({ type: 'state_sync', seq: 0, simMs: 0, locked: false })
  })
  return ws
}

beforeEach(() => {
  useSessionStore.setState({ team: null, facilitator: { sessionCode: 'ABC234', token: 'fac' } })
  useSessionLiveStore.getState().reset()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  useSessionStore.setState({ team: null, facilitator: null })
})

describe('facilitator official run', () => {
  it('starts after a confirm, shows each team running, and stops them all', async () => {
    const fetchMock = mockApi({
      'GET /api/sessions/ABC234': { body: detail },
      'GET /api/sessions/ABC234/leaderboard': { body: [] },
      'POST /api/sessions/ABC234/runs': {
        status: 201,
        body: { seed: 7, runs: [{ runId: 'r1', status: 'running' }, { runId: 'b1', status: 'failed' }] },
      },
      'POST /api/runs/r1/stop': { body: {} },
    })
    render(<FacilitatorPage />)
    const ws = goLive()
    expect(FakeWebSocket.latest().sent[0]).toEqual({ type: 'auth', token: 'fac' })
    await screen.findByText('No official run yet.') // the leaderboard loads once live

    fireEvent.click(screen.getByRole('button', { name: 'Start official run' }))
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    expect(await screen.findByText('Started for 2 teams (seed 7). 1 graph has errors and ranked last.')).toBeTruthy()

    act(() => ws.receive(started('red', 'r1')))
    const red = (await screen.findByText('Red')).closest('tr')!
    expect(within(red).getByText('Official · running')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toBe('Playing…')

    fireEvent.click(screen.getByRole('button', { name: 'Stop all' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url) === '/api/runs/r1/stop')).toBe(true))
  })

  it('cancelling the confirm starts nothing', async () => {
    const fetchMock = mockApi({ 'GET /api/sessions/ABC234': { body: detail }, 'GET /api/sessions/ABC234/leaderboard': { body: [] } })
    render(<FacilitatorPage />)
    goLive()
    fireEvent.click(await screen.findByRole('button', { name: 'Start official run' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })

  it('reports an official run already playing (409)', async () => {
    mockApi({
      'GET /api/sessions/ABC234': { body: detail },
      'GET /api/sessions/ABC234/leaderboard': { body: [] },
      'POST /api/sessions/ABC234/runs': { status: 409, body: { detail: 'busy' } },
    })
    render(<FacilitatorPage />)
    goLive()
    fireEvent.click(await screen.findByRole('button', { name: 'Start official run' }))
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    expect((await screen.findByText('An official run is already in progress.')).getAttribute('role')).toBe('alert')
  })

  it('updates the leaderboard from the stream', async () => {
    mockApi({ 'GET /api/sessions/ABC234': { body: detail }, 'GET /api/sessions/ABC234/leaderboard': { body: [] } })
    render(<FacilitatorPage />)
    const ws = goLive()
    await screen.findByText('No official run yet.')
    act(() => ws.receive({ type: 'leaderboard_updated', seq: 0, simMs: 0, rows: board }))
    const table = screen.getAllByRole('table').find((t) => t.className.includes('leaderboard'))!
    expect(within(table).getAllByRole('row')[1].textContent).toContain('Red77')
  })
})

describe('/screen', () => {
  it('asks for the facilitator sign-in first', () => {
    useSessionStore.setState({ facilitator: null })
    render(<ScreenPage />)
    expect(screen.getByRole('link', { name: 'facilitator page' })).toBeTruthy()
    expect(FakeWebSocket.instances).toHaveLength(0)
  })

  it('shows how to join, the leaderboard large and a live tile per team', async () => {
    mockApi({ 'GET /api/sessions/ABC234': { body: detail }, 'GET /api/sessions/ABC234/leaderboard': { body: board } })
    render(<ScreenPage />)
    const ws = goLive()
    expect(screen.getByText('ABC234')).toBeTruthy()
    const table = await screen.findByRole('table')
    expect(table.className).toContain('leaderboard--large')
    act(() => {
      ws.receive(started('red', 'r1'))
      ws.receive({ type: 'metrics_snapshot', runId: 'r1', teamId: 'red', seq: 3, simMs: 1, metrics, nodeStats: [] })
    })
    const tile = await screen.findByRole('group', { name: 'Red' })
    expect(tile.textContent).toContain('official run playing')
    expect(tile.textContent).toContain('650 ms')
    expect(screen.getByRole('group', { name: 'Blue' }).textContent).toContain('waiting')
  })
})
