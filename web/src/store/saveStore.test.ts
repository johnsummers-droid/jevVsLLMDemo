import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { catalogByType, catalogNodes, defaultGraphFixture } from '../test/fixtures'
import { mockApi } from '../test/mockApi'
import type { Graph, StoredGraph } from '../types'
import { useCatalogStore } from './catalogStore'
import { useGraphStore } from './graphStore'
import {
  RELOADED_NOTICE,
  RETRY_BASE_MS,
  SAVE_DEBOUNCE_MS,
  startAutosave,
  SYNC_POLL_MS,
  useSaveStore,
} from './saveStore'
import { useSessionStore } from './sessionStore'

const GRAPH_URL = '/api/teams/t1/graph'

function stored(version: number, graph: Graph = defaultGraphFixture, locked = false): StoredGraph {
  return { teamId: 't1', version, locked, graph, updatedAt: '2026-10-26T09:00:00Z' }
}

const graph = () => useGraphStore.getState()
const firstNodeId = defaultGraphFixture.nodes[0].id
const move = (x: number) => graph().moveNode(firstNodeId, { x, y: 0 })
const puts = (fetchMock: ReturnType<typeof vi.fn>) =>
  fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'PUT')
const putBody = (call: unknown[]) => JSON.parse(String((call[1] as RequestInit).body)) as { version: number; graph: Graph }

let stop: () => void

beforeEach(() => {
  vi.useFakeTimers()
  useCatalogStore.setState({ status: 'ready', nodes: catalogNodes, byType: catalogByType, error: null })
  useSessionStore.setState({ team: { sessionCode: 'ABC234', teamId: 't1', teamName: 'Red', token: 'tok' } })
  graph().clear()
  graph().setStoredGraph(stored(0))
  stop = startAutosave()
})

afterEach(() => {
  stop()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  useSessionStore.setState({ team: null, facilitator: null })
})

/** A PUT handler that answers with the next version of whatever was sent. */
function acceptSaves() {
  return (init: RequestInit) => {
    const body = JSON.parse(String(init.body)) as { version: number; graph: Graph }
    return { body: stored(body.version + 1, body.graph) }
  }
}

describe('autosave', () => {
  it('does not save a graph that was just loaded', async () => {
    const fetchMock = mockApi({})
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS * 3)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(useSaveStore.getState().status).toBe('saved')
  })

  it('saves once, SAVE_DEBOUNCE_MS after the last change, positions included', async () => {
    const fetchMock = mockApi({ [`PUT ${GRAPH_URL}`]: acceptSaves() })
    move(100)
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS - 100)
    move(200)
    expect(useSaveStore.getState().status).toBe('pending')
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS - 100)
    expect(fetchMock).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(100)
    expect(puts(fetchMock)).toHaveLength(1)
    const body = putBody(puts(fetchMock)[0])
    expect(body.version).toBe(0)
    expect(body.graph.nodes[0].position).toEqual({ x: 200, y: 0 })
    expect(graph().version).toBe(1)
    expect(useSaveStore.getState().status).toBe('saved')
  })

  it('keeps one request in flight and saves changes made meanwhile after it', async () => {
    let release: () => void = () => {}
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body)) as { version: number; graph: Graph }
      if (body.version === 0) await new Promise<void>((resolve) => (release = resolve))
      return new Response(JSON.stringify(stored(body.version + 1, body.graph)), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)

    move(100)
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS)
    expect(useSaveStore.getState().status).toBe('saving')
    move(200)
    move(300)
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS * 5)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    release()
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const second = putBody(fetchMock.mock.calls[1])
    expect(second.version).toBe(1)
    expect(second.graph.nodes[0].position).toEqual({ x: 300, y: 0 })
    expect(graph().version).toBe(2)
    expect(useSaveStore.getState().status).toBe('saved')
  })

  it('409 loads the server graph from the response, with a notice', async () => {
    const theirs: Graph = { ...defaultGraphFixture, nodes: defaultGraphFixture.nodes.slice(0, 2), edges: [] }
    const fetchMock = mockApi({ [`PUT ${GRAPH_URL}`]: { status: 409, body: stored(5, theirs) } })
    move(100)
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS)
    expect(graph().version).toBe(5)
    expect(graph().nodes.map((n) => n.id)).toEqual(theirs.nodes.map((n) => n.id))
    expect(graph().notice).toBe(RELOADED_NOTICE)
    expect(useSaveStore.getState().status).toBe('saved')
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS * 3)
    expect(puts(fetchMock)).toHaveLength(1)
  })

  it('423 makes the graph read-only, then saves the edits once the server unlocks it', async () => {
    let locked = true
    const fetchMock = mockApi({
      [`PUT ${GRAPH_URL}`]: (init) => (locked ? { status: 423, body: { detail: 'graph is locked' } } : acceptSaves()(init)),
      [`GET ${GRAPH_URL}`]: () => ({ body: stored(0, defaultGraphFixture, locked) }),
    })
    move(100)
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS)
    expect(graph().locked).toBe(true)
    expect(useSaveStore.getState().status).toBe('locked')

    // Edits are refused while locked.
    expect(graph().addNode('policy', { x: 0, y: 0 })).toBe('')
    move(999)
    expect(graph().nodes[0].position).toEqual({ x: 100, y: 0 })

    await vi.advanceTimersByTimeAsync(SYNC_POLL_MS)
    expect(graph().locked).toBe(true)
    locked = false
    await vi.advanceTimersByTimeAsync(SYNC_POLL_MS)
    expect(graph().locked).toBe(false)
    expect(puts(fetchMock)).toHaveLength(2)
    expect(putBody(puts(fetchMock)[1]).graph.nodes[0].position).toEqual({ x: 100, y: 0 })
    expect(useSaveStore.getState().status).toBe('saved')
  })

  it('a graph that loads locked is read-only from the start', async () => {
    stop()
    graph().setStoredGraph(stored(3, defaultGraphFixture, true))
    stop = startAutosave()
    expect(useSaveStore.getState().status).toBe('locked')
    const check = graph().connect({ source: 'a', sourceHandle: 'x', target: 'b', targetHandle: 'y' })
    expect(check).toMatchObject({ ok: false, reason: 'locked' })
  })

  it('retries with backoff after a network error and shows offline', async () => {
    let failures = 2
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      if (failures-- > 0) throw new TypeError('Failed to fetch')
      const body = JSON.parse(String(init.body)) as { version: number; graph: Graph }
      return new Response(JSON.stringify(stored(body.version + 1, body.graph)), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)
    move(100)
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS)
    expect(useSaveStore.getState().status).toBe('offline')
    move(150) // edits while offline wait for the retry
    await vi.advanceTimersByTimeAsync(RETRY_BASE_MS)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(useSaveStore.getState().status).toBe('offline')
    await vi.advanceTimersByTimeAsync(RETRY_BASE_MS * 2 - 1)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(putBody(fetchMock.mock.calls[2]).graph.nodes[0].position).toEqual({ x: 150, y: 0 })
    expect(useSaveStore.getState().status).toBe('saved')
  })

  it('sends a pending save with keepalive at pagehide', async () => {
    const fetchMock = mockApi({ [`PUT ${GRAPH_URL}`]: acceptSaves() })
    move(100)
    window.dispatchEvent(new Event('pagehide'))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'PUT', keepalive: true })
  })

  it('flush saves pending changes right away', async () => {
    const fetchMock = mockApi({ [`PUT ${GRAPH_URL}`]: acceptSaves() })
    move(100)
    await useSaveStore.getState().flush()
    expect(puts(fetchMock)).toHaveLength(1)
    expect(graph().version).toBe(1)
  })

  it('reset loads the default graph the server returns', async () => {
    const fetchMock = mockApi({
      [`PUT ${GRAPH_URL}`]: acceptSaves(),
      [`POST ${GRAPH_URL}/reset`]: { body: stored(7) },
    })
    graph().deleteNode(firstNodeId)
    await useSaveStore.getState().reset()
    expect(graph().version).toBe(7)
    expect(graph().nodes).toHaveLength(defaultGraphFixture.nodes.length)
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS * 3)
    expect(puts(fetchMock)).toHaveLength(0)
    expect(useSaveStore.getState().status).toBe('saved')
  })

  it('an idle team sees the lock and the unlock through the sync poll', async () => {
    let locked = false
    mockApi({ [`GET ${GRAPH_URL}`]: () => ({ body: stored(0, defaultGraphFixture, locked) }) })
    locked = true
    await vi.advanceTimersByTimeAsync(SYNC_POLL_MS)
    expect(graph().locked).toBe(true)
    expect(useSaveStore.getState().status).toBe('locked')
    locked = false
    await vi.advanceTimersByTimeAsync(SYNC_POLL_MS)
    expect(graph().locked).toBe(false)
    expect(useSaveStore.getState().status).toBe('saved')
  })

  it("an idle tab loads another tab's newer save, but never over unsaved edits", async () => {
    const theirs: Graph = { ...defaultGraphFixture, nodes: defaultGraphFixture.nodes.slice(0, 2), edges: [] }
    const fetchMock = mockApi({
      [`GET ${GRAPH_URL}`]: { body: stored(3, theirs) },
      [`PUT ${GRAPH_URL}`]: { status: 409, body: stored(3, theirs) },
    })
    move(100) // unsaved: the poll leaves it alone, the save's 409 reloads
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS - 1)
    await vi.advanceTimersByTimeAsync(1)
    expect(puts(fetchMock)).toHaveLength(1)
    expect(graph().version).toBe(3)

    graph().setStoredGraph(stored(2)) // as if this tab were behind and idle
    graph().setNotice(null)
    await vi.advanceTimersByTimeAsync(SYNC_POLL_MS)
    expect(graph().version).toBe(3)
    expect(graph().nodes).toHaveLength(2)
    expect(graph().notice).toBe(RELOADED_NOTICE)
  })

  it('a reload restores the saved graph (M3 exit)', async () => {
    let server = stored(0)
    mockApi({
      [`GET ${GRAPH_URL}`]: () => ({ body: server }),
      [`PUT ${GRAPH_URL}`]: (init) => {
        const body = JSON.parse(String(init.body)) as { version: number; graph: Graph }
        server = stored(body.version + 1, body.graph)
        return { body: server }
      },
    })
    const id = graph().addNode('knowledge_lookup', { x: 500, y: 500 })
    move(42)
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS)
    const before = graph().toGraph()

    stop()
    graph().clear()
    await graph().loadTeamGraph('t1')
    stop = startAutosave()
    expect(graph().toGraph()).toEqual(before)
    expect(graph().nodes.some((n) => n.id === id)).toBe(true)
    expect(graph().version).toBe(1)
  })
})
