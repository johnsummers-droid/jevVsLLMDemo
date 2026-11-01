// T40: the facilitator's reference graph view and the team's post-run reveal.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import strongGraph from '../../../shared/fixtures/graphs/strong.json'
import App from '../App'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { useRunStore } from '../store/runStore'
import { useSessionStore } from '../store/sessionStore'
import { catalogNodes, defaultGraphFixture } from '../test/fixtures'
import { authHeader, mockApi, type Route } from '../test/mockApi'
import { ReferenceGraphView } from './ReferenceGraphView'

const team = { sessionCode: 'ABC234', teamId: 't1', teamName: 'Red', token: 'tok' }
const graphs = [
  { name: 'default', label: 'Starter (default)' },
  { name: 'strong', label: 'Strong' },
]

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.stubGlobal('DOMMatrixReadOnly', class { m22 = 1 })
  useSessionStore.setState({ team: null, facilitator: null })
  useGraphStore.getState().clear()
  useCatalogStore.setState({ status: 'idle', nodes: [], byType: {} })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/')
})

describe('ReferenceGraphView', () => {
  const session = '/api/sessions/ABC234/reference-graphs'

  function start(routes: Record<string, Route> = {}) {
    useSessionStore.setState({ facilitator: { sessionCode: 'ABC234', token: 'fac' } })
    const fetchMock = mockApi({
      'GET /api/catalog': { body: { nodes: catalogNodes } },
      [`GET ${session}`]: { body: { available: true, graphs } },
      [`GET ${session}/strong`]: { body: strongGraph },
      ...routes,
    })
    render(<ReferenceGraphView sessionCode="ABC234" />)
    return fetchMock
  }

  it('shows nothing until a graph is picked, then fetches it with the facilitator token', async () => {
    const fetchMock = start()
    const picker = (await screen.findByRole('combobox')) as HTMLSelectElement
    await screen.findByRole('option', { name: 'Strong' })
    expect(picker.value).toBe('')
    expect(screen.queryByRole('group')).toBeNull()

    fireEvent.change(picker, { target: { value: 'strong' } })
    await screen.findByRole('group', { name: 'Reference graph strong' })
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith(`${session}/strong`))
    expect(authHeader(call?.[1] as RequestInit)).toBe('Bearer fac')
    // It has a canvas of its own: nothing lands in the team's graph store.
    expect(useGraphStore.getState().nodes).toHaveLength(0)

    fireEvent.change(picker, { target: { value: '' } })
    await waitFor(() => expect(screen.queryByRole('group')).toBeNull())
  })

  it('says so when a graph cannot be loaded', async () => {
    start({ [`GET ${session}/strong`]: { status: 500, body: { detail: 'boom' } } })
    const picker = await screen.findByRole('combobox')
    await screen.findByRole('option', { name: 'Strong' })
    fireEvent.change(picker, { target: { value: 'strong' } })
    expect((await screen.findByRole('alert')).textContent).toMatch(/Could not load/)
  })
})

describe('the reveal on the team page', () => {
  let serverLocked = false

  function start(locked: boolean, available: boolean) {
    serverLocked = locked
    useSessionStore.setState({ team })
    window.history.replaceState(null, '', '/team')
    const stored = () => ({ teamId: 't1', version: 0, locked: serverLocked, graph: defaultGraphFixture, updatedAt: '2026-11-01T09:00:00Z' })
    const fetchMock = mockApi({
      'GET /api/catalog': { body: { nodes: catalogNodes } },
      'GET /api/teams/t1/graph': () => ({ body: stored() }),
      'GET /api/teams/t1/reference-graphs': { body: available ? { available, graphs } : { available, graphs: [] } },
      'GET /api/teams/t1/reference-graphs/strong': { body: strongGraph },
      'POST /api/graphs/validate': { body: { ok: true, issues: [] } },
    })
    render(<App />)
    return fetchMock
  }

  const asked = (fetchMock: ReturnType<typeof mockApi>) =>
    fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/api/teams/t1/reference-graphs')).length

  it('does not ask while the team is editing', async () => {
    const fetchMock = start(false, false)
    await waitFor(() => expect(useGraphStore.getState().status).toBe('ready'))
    expect(asked(fetchMock)).toBe(0)
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('stays hidden while locked if the server says not yet', async () => {
    const fetchMock = start(true, false)
    await waitFor(() => expect(asked(fetchMock)).toBeGreaterThan(0))
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('offers the graphs after the official run and shows one read-only, with no run numbers', async () => {
    start(true, true)
    const picker = (await screen.findByRole('combobox', { name: /View reference graph/ })) as HTMLSelectElement
    useRunStore.setState({ run: { runId: 'r' } as never, nodeStats: { router: { requests: 9 } as never } })
    fireEvent.change(picker, { target: { value: 'strong' } })
    await waitFor(() => expect(useGraphStore.getState().reference).toBe('strong'))
    expect(screen.getByText(/Viewing the reference graph/)).toBeTruthy()
    expect(useGraphStore.getState().addNode('human_review_queue', { x: 0, y: 0 })).toBe('')
    expect(screen.queryByLabelText('Run statistics')).toBeNull()

    fireEvent.change(picker, { target: { value: '' } })
    await waitFor(() => expect(useGraphStore.getState().reference).toBeNull())
    expect(useGraphStore.getState().nodes).toHaveLength(defaultGraphFixture.nodes.length)
    useRunStore.setState({ run: null, nodeStats: {} })
  })

  it('goes back to the team graph when the session is unlocked', async () => {
    start(true, true)
    const picker = await screen.findByRole('combobox', { name: /View reference graph/ })
    fireEvent.change(picker, { target: { value: 'strong' } })
    await waitFor(() => expect(useGraphStore.getState().reference).toBe('strong'))
    serverLocked = false
    useGraphStore.getState().setLocked(false)
    await waitFor(() => expect(useGraphStore.getState().reference).toBeNull())
    await waitFor(() => expect(screen.queryByRole('combobox')).toBeNull())
  })
})
