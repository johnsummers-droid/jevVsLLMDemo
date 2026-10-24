// Typed fetch wrapper for the FastAPI server. In development Vite proxies /api to port 8000; a
// deployed build sets VITE_API_URL to the server's origin. The team token arrives with M3.
import type { CatalogResponse, Graph, ValidationReport } from '../types'

const BASE_URL: string = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, body: unknown, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const response = await fetch(BASE_URL + path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await response.text()
  let data: unknown = undefined
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!response.ok) {
    throw new ApiError(response.status, data, `${method} ${path} failed with ${response.status}`)
  }
  return data as T
}

export const api = {
  getCatalog: () => request<CatalogResponse>('GET', '/api/catalog'),
  getDefaultGraph: () => request<Graph>('GET', '/api/graphs/default'),
  validateGraph: (graph: Graph) => request<ValidationReport>('POST', '/api/graphs/validate', graph),
}
