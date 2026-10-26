// A fetch stub that answers by "METHOD /path" (query string ignored). Unrouted requests get 404.
import { vi } from 'vitest'

export type Reply = { status?: number; body?: unknown }
export type Route = Reply | ((init: RequestInit) => Reply)

export function mockApi(routes: Record<string, Route>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const path = String(input).split('?')[0]
    const route = routes[`${init.method ?? 'GET'} ${path}`]
    const reply = typeof route === 'function' ? route(init) : (route ?? { status: 404, body: { detail: 'not found' } })
    const text = reply.body === undefined ? '' : JSON.stringify(reply.body)
    return new Response(text, { status: reply.status ?? 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** The Authorization header the client sent with a call. */
export function authHeader(init: RequestInit | undefined): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.Authorization
}
