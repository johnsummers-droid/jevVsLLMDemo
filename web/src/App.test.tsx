import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { navigate } from './lib/navigation'
import { useGraphStore } from './store/graphStore'
import { useSessionStore } from './store/sessionStore'
import { catalogNodes, defaultGraphFixture } from './test/fixtures'
import { mockApi } from './test/mockApi'

const team = { sessionCode: 'ABC234', teamId: 't1', teamName: 'Red', token: 'tok' }
const stored = { teamId: 't1', version: 0, locked: false, graph: defaultGraphFixture, updatedAt: '2026-10-26T09:00:00Z' }

// jsdom has no ResizeObserver or DOMMatrixReadOnly; React Flow uses both once the canvas mounts.
function stubCanvasDom() {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
  vi.stubGlobal(
    'DOMMatrixReadOnly',
    class {
      m22 = 1
    },
  )
}

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
    stubCanvasDom()
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

  it('collapses and expands the side panels, with the carets pointing the right way', async () => {
    useSessionStore.setState({ team })
    window.history.replaceState(null, '', '/team')
    stubCanvasDom()
    mockApi({
      'GET /api/catalog': { body: { nodes: catalogNodes } },
      'GET /api/teams/t1/graph': { body: stored },
      'POST /api/graphs/validate': { body: { ok: true, issues: [] } },
    })
    render(<App />)
    await waitFor(() => expect(useGraphStore.getState().status).toBe('ready'))

    const left = screen.getByRole('button', { name: 'Collapse node palette' })
    const right = screen.getByRole('button', { name: 'Collapse node information panel' })
    // Open: each caret points to its nearest outer edge.
    expect(left.dataset.points).toBe('left')
    expect(right.dataset.points).toBe('right')
    expect(screen.getByRole('complementary', { name: 'Node palette' })).toBeTruthy()

    fireEvent.click(left)
    expect(screen.queryByRole('complementary', { name: 'Node palette' })).toBeNull()
    expect(left.getAttribute('aria-label')).toBe('Expand node palette')
    expect(left.getAttribute('aria-expanded')).toBe('false')
    expect(left.dataset.points).toBe('right') // towards the canvas's centre
    expect(right.dataset.points).toBe('right') // the other panel is untouched

    fireEvent.click(right)
    expect(right.dataset.points).toBe('left')
    expect(screen.queryByRole('heading', { name: 'Pipeline check' })).toBeNull()

    fireEvent.click(left)
    expect(screen.getByRole('complementary', { name: 'Node palette' })).toBeTruthy()
    expect(left.dataset.points).toBe('left')
  })

  it('a locked graph shows the banner and disables editing', async () => {
    useSessionStore.setState({ team })
    window.history.replaceState(null, '', '/team')
    stubCanvasDom()
    mockApi({
      'GET /api/catalog': { body: { nodes: catalogNodes } },
      'GET /api/teams/t1/graph': { body: { ...stored, locked: true } },
      'POST /api/graphs/validate': { body: { ok: true, issues: [] } },
    })
    render(<App />)
    expect((await screen.findByRole('alert')).textContent).toMatch(/Pencils down/)
    expect(screen.getByText('Locked')).toBeTruthy()
    expect(screen.getByRole('img', { name: 'This graph is locked' })).toBeTruthy()
    const card = screen.getByRole('button', { name: /^Knowledge lookup/ }) as HTMLButtonElement
    expect(card.disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Reset graph' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('the help panel opens over the canvas and the workbench keeps working under it', async () => {
    useSessionStore.setState({ team })
    window.history.replaceState(null, '', '/team')
    stubCanvasDom()
    mockApi({
      'GET /api/catalog': { body: { nodes: catalogNodes } },
      'GET /api/teams/t1/graph': { body: stored },
      'POST /api/graphs/validate': { body: { ok: true, issues: [] } },
    })
    render(<App />)
    await waitFor(() => expect(useGraphStore.getState().status).toBe('ready'))
    fireEvent.click(screen.getByRole('button', { name: 'Help: Policy engine' }))
    const panel = screen.getByRole('complementary', { name: 'Help: Policy engine' })
    expect(panel.closest('.app__canvas')?.classList.contains('app__canvas--help-open')).toBe(true)
    const before = useGraphStore.getState().nodes.length
    fireEvent.click(screen.getByRole('button', { name: /^Knowledge lookup/ }))
    expect(useGraphStore.getState().nodes).toHaveLength(before + 1)
    expect(screen.getByRole('complementary', { name: 'Help: Policy engine' })).toBeTruthy()
  })

  it('reset asks for confirmation, then loads the default graph', async () => {
    useSessionStore.setState({ team })
    window.history.replaceState(null, '', '/team')
    stubCanvasDom()
    const small = { ...defaultGraphFixture, nodes: defaultGraphFixture.nodes.slice(0, 1), edges: [] }
    const fetchMock = mockApi({
      'GET /api/catalog': { body: { nodes: catalogNodes } },
      'GET /api/teams/t1/graph': { body: { ...stored, version: 4, graph: small } },
      'POST /api/teams/t1/graph/reset': { body: { ...stored, version: 5 } },
      'POST /api/graphs/validate': { body: { ok: true, issues: [] } },
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Reset graph' }))
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/reset'))).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
    await waitFor(() => expect(useGraphStore.getState().version).toBe(5))
    expect(useGraphStore.getState().nodes).toHaveLength(defaultGraphFixture.nodes.length)
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
