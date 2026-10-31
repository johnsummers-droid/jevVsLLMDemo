// TEMPORARY ?ref reference-graph viewer (lib/referenceGraphs.ts).
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import strongGraph from '../../../shared/fixtures/graphs/strong.json'
import App from '../App'
import { referenceViewerEnabled } from '../lib/referenceGraphs'
import { useGraphStore } from '../store/graphStore'
import { useSessionStore } from '../store/sessionStore'
import { catalogNodes, defaultGraphFixture } from '../test/fixtures'
import { mockApi } from '../test/mockApi'
import type { Graph } from '../types'

const team = { sessionCode: 'ABC234', teamId: 't1', teamName: 'Red', token: 'tok' }

function stubCanvasDom() {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.stubGlobal('DOMMatrixReadOnly', class { m22 = 1 })
}

function startTeamPage(path: string) {
  useSessionStore.setState({ team })
  window.history.replaceState(null, '', path)
  stubCanvasDom()
  let saved: Graph = defaultGraphFixture
  let version = 0
  const stored = () => ({ teamId: 't1', version, locked: false, graph: saved, updatedAt: '2026-10-31T09:00:00Z' })
  const fetchMock = mockApi({
    'GET /api/catalog': { body: { nodes: catalogNodes } },
    'GET /api/teams/t1/graph': () => ({ body: stored() }),
    'PUT /api/teams/t1/graph': (init) => {
      saved = JSON.parse(String(init.body)).graph
      version += 1
      return { body: stored() }
    },
    'POST /api/graphs/validate': { body: { ok: true, issues: [] } },
  })
  render(<App />)
  return { fetchMock, saved: () => saved }
}

const puts = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'PUT').length

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

describe('reference graph viewer (?ref)', () => {
  it('is enabled only by ?ref', () => {
    expect(referenceViewerEnabled('?ref')).toBe(true)
    expect(referenceViewerEnabled('?ref=1&x=2')).toBe(true)
    expect(referenceViewerEnabled('')).toBe(false)
  })

  it('is hidden without ?ref', async () => {
    startTeamPage('/team')
    await waitFor(() => expect(useGraphStore.getState().status).toBe('ready'))
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('saves the canvas, shows the reference read-only, and "User defined" brings the saved graph back', async () => {
    const { fetchMock, saved } = startTeamPage('/team?ref')
    await waitFor(() => expect(useGraphStore.getState().status).toBe('ready'))
    const picker = screen.getByRole('combobox') as HTMLSelectElement
    expect(picker.value).toBe('')

    // An edit that autosave has not sent yet.
    useGraphStore.getState().moveNode('router', { x: 999, y: 999 })
    fireEvent.change(picker, { target: { value: 'strong' } })

    await waitFor(() => expect(useGraphStore.getState().reference).toBe('strong'))
    expect(saved().nodes.find((n) => n.id === 'router')?.position).toEqual({ x: 999, y: 999 })
    expect(useGraphStore.getState().nodes.map((n) => n.id).sort()).toEqual(
      (strongGraph as Graph).nodes.map((n) => n.id).sort(),
    )
    expect(screen.getByText(/Viewing the reference graph/)).toBeTruthy()
    expect(useGraphStore.getState().addNode('human_review_queue', { x: 0, y: 0 })).toBe('')
    expect(screen.getByRole('button', { name: 'Reset graph' })).toHaveProperty('disabled', true)

    // The reference graph is never saved.
    const savesSoFar = puts(fetchMock)
    await new Promise((resolve) => setTimeout(resolve, 1200))
    expect(puts(fetchMock)).toBe(savesSoFar)

    fireEvent.change(picker, { target: { value: '' } })
    await waitFor(() => expect(useGraphStore.getState().reference).toBeNull())
    const router = useGraphStore.getState().nodes.find((n) => n.id === 'router')
    expect(router?.position).toEqual({ x: 999, y: 999 })
    expect(useGraphStore.getState().nodes).toHaveLength(defaultGraphFixture.nodes.length)
    expect(screen.queryByText(/Viewing the reference graph/)).toBeNull()
  })
})
