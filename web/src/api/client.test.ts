import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from './client'

function stubFetch(status: number, body: string) {
  const fetchMock = vi.fn(async () => new Response(body, { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

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
})
