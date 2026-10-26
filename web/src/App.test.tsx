import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { navigate } from './lib/navigation'
import { useGraphStore } from './store/graphStore'
import { useSessionStore } from './store/sessionStore'
import { catalogNodes, defaultGraphFixture } from './test/fixtures'
import { mockApi } from './test/mockApi'

const team = { sessionCode: 'ABC234', teamId: 't1', teamName: 'Red', token: 'tok' }
const stored = { teamId: 't1', version: 0, locked: false, graph: defaultGraphFixture, updatedAt: '2026-10-26T09:00:00Z' }

beforeEach(() => {
  window.localStorage.clear()
  useSessionStore.setState({ team: null, facilitator: null })
  useGraphStore.getState().clear()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/')
})

describe('App pages', () => {
  it('sends "/" and unknown paths to /join without a team', async () => {
    for (const path of ['/', '/nowhere']) {
      window.history.replaceState(null, '', path)
      render(<App />)
      await screen.findByRole('heading', { name: 'Join the workshop' })
      expect(window.location.pathname).toBe('/join')
      cleanup()
    }
  })

  it('/team without a team goes to /join', async () => {
    window.history.replaceState(null, '', '/team')
    render(<App />)
    await screen.findByRole('heading', { name: 'Join the workshop' })
    expect(window.location.pathname).toBe('/join')
  })

  it("/team loads the team's stored graph", async () => {
    useSessionStore.setState({ team })
    window.history.replaceState(null, '', '/')
    // jsdom has no ResizeObserver; React Flow needs one once the canvas mounts.
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    )
    const fetchMock = mockApi({
      'GET /api/catalog': { body: { nodes: catalogNodes } },
      'GET /api/teams/t1/graph': { body: stored },
      'POST /api/graphs/validate': { body: { ok: true, issues: [] } },
    })
    render(<App />)
    expect(window.location.pathname).toBe('/team')
    await waitFor(() => expect(useGraphStore.getState().status).toBe('ready'))
    expect(useGraphStore.getState().nodes).toHaveLength(defaultGraphFixture.nodes.length)
    expect(screen.getByText('Red')).toBeTruthy()
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/graphs/default')).toBe(false)
  })

  it('a 401 on /team returns to /join', async () => {
    useSessionStore.setState({ team })
    window.history.replaceState(null, '', '/team')
    mockApi({
      'GET /api/catalog': { body: { nodes: catalogNodes } },
      'GET /api/teams/t1/graph': { status: 401, body: { detail: 'invalid or revoked token' } },
    })
    render(<App />)
    await screen.findByRole('heading', { name: 'Join the workshop' })
    expect(window.location.pathname).toBe('/join')
    expect(useSessionStore.getState().team).toBeNull()
  })

  it('follows navigation between pages', async () => {
    window.history.replaceState(null, '', '/join')
    render(<App />)
    await screen.findByRole('heading', { name: 'Join the workshop' })
    act(() => navigate('/facilitator'))
    await screen.findByRole('heading', { name: 'Start a workshop session' })
  })
})
