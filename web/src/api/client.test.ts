import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from '../store/sessionStore'
import { authHeader, mockApi } from '../test/mockApi'
import { ApiError, api } from './client'

function stubFetch(status: number, body: string) {
  const fetchMock = vi.fn(async () => new Response(body, { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
  useSessionStore.setState({ team: null, facilitator: null })
  window.history.replaceState(null, '', '/')
})

const team = { sessionCode: 'ABC234', teamId: 't1', teamName: 'Red', token: 'team-token' }
const facilitator = { sessionCode: 'ABC234', token: 'fac-token' }

describe('api client', () => {
  it('parses a JSON response', async () => {
    const fetchMock = stubFetch(200, '{"nodes": []}')
    await expect(api.getCatalog()).resolves.toEqual({ nodes: [] })
    expect(fetchMock).toHaveBeenCalledWith('/api/catalog', expect.objectContaining({ method: 'GET' }))
  })

  it('posts the graph as JSON', async () => {
    const fetchMock = stubFetch(200, '{"ok": true, "issues": []}')
    const graph = { schemaVersion: 1 as const, nodes: [], edges: [] }
    await api.validateGraph(graph)
    expect(fetchMock).toHaveBeenCalledWith('/api/graphs/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(graph),
    })
  })

  it('throws ApiError with the status and parsed body', async () => {
    stubFetch(422, '{"detail": "bad"}')
    const error = await api.getDefaultGraph().catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 422, body: { detail: 'bad' } })
  })

  it('keeps a non-JSON error body as text', async () => {
    stubFetch(502, 'Bad Gateway')
    await expect(api.getCatalog()).rejects.toMatchObject({ status: 502, body: 'Bad Gateway' })
  })

  it("sends each role's bearer token", async () => {
    useSessionStore.setState({ team, facilitator })
    const fetchMock = mockApi({
      'GET /api/teams/t1/graph': { body: {} },
      'GET /api/sessions/ABC234': { body: {} },
      'POST /api/sessions/ABC234/teams': { status: 201, body: {} },
    })
    await api.getTeamGraph('t1')
    await api.getSession('ABC234')
    await api.joinTeam('ABC234', 'Red')
    expect(fetchMock.mock.calls.map(([, init]) => authHeader(init))).toEqual([
      'Bearer team-token',
      'Bearer fac-token',
      undefined,
    ])
  })

  it('a 401 signs the team out and returns to /join', async () => {
    useSessionStore.setState({ team, facilitator })
    window.history.replaceState(null, '', '/team')
    mockApi({ 'GET /api/teams/t1/graph': { status: 401, body: { detail: 'invalid or revoked token' } } })
    await expect(api.getTeamGraph('t1')).rejects.toMatchObject({ status: 401 })
    expect(useSessionStore.getState()).toMatchObject({ team: null, facilitator })
    expect(window.location.pathname).toBe('/join')
  })

  it('a 401 signs the facilitator out and returns to /facilitator', async () => {
    useSessionStore.setState({ team, facilitator })
    mockApi({ 'GET /api/sessions/ABC234': { status: 401 } })
    await expect(api.getSession('ABC234')).rejects.toBeInstanceOf(ApiError)
    expect(useSessionStore.getState()).toMatchObject({ team, facilitator: null })
    expect(window.location.pathname).toBe('/facilitator')
  })

  it('a 401 on an unauthenticated call signs nobody out', async () => {
    useSessionStore.setState({ team, facilitator })
    mockApi({ 'POST /api/sessions': { status: 401, body: { detail: 'wrong facilitator code' } } })
    await expect(api.createSession('nope')).rejects.toMatchObject({ status: 401 })
    expect(useSessionStore.getState()).toMatchObject({ team, facilitator })
    expect(window.location.pathname).toBe('/')
  })
})
