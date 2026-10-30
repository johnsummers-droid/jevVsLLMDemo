// Typed fetch wrapper for the FastAPI server. In development Vite proxies /api to port 8000; a
// deployed build sets VITE_API_BASE_URL to the server's origin. Requests made as a team or as the
// facilitator carry that role's bearer token; a 401 on one signs the role out and returns to its
// sign-in page.
import { navigate, PATHS } from '../lib/navigation'
import { type Role, useSessionStore } from '../store/sessionStore'
import type {
  CatalogResponse,
  CreateSessionResponse,
  Graph,
  JoinTeamResponse,
  PackSummary,
  RunRecord,
  SaveGraphRequest,
  SessionDetail,
  StoredGraph,
  ValidationReport,
} from '../types'

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? ''

const SIGN_IN_PAGE: Record<Role, string> = { team: PATHS.join, facilitator: PATHS.facilitator }

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

/** Forgets the role's credentials and goes to its sign-in page (a 401, or a refused live socket). */
export function signOutTo(role: Role): void {
  useSessionStore.getState().signOut(role)
  navigate(SIGN_IN_PAGE[role], { replace: true })
}

function token(role: Role): string | undefined {
  const state = useSessionStore.getState()
  return (role === 'team' ? state.team : state.facilitator)?.token
}

async function request<T>(
  method: 'GET' | 'POST' | 'PUT',
  path: string,
  body?: unknown,
  role?: Role,
  { keepalive = false }: { keepalive?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const bearer = role && token(role)
  if (bearer) headers.Authorization = `Bearer ${bearer}`
  const response = await fetch(BASE_URL + path, {
    method,
    headers: Object.keys(headers).length ? headers : undefined,
    body: body === undefined ? undefined : JSON.stringify(body),
    ...(keepalive && { keepalive }),
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
    if (response.status === 401 && role) signOutTo(role)
    throw new ApiError(response.status, data, `${method} ${path} failed with ${response.status}`)
  }
  return data as T
}

const code = (sessionCode: string) => encodeURIComponent(sessionCode)
const teamGraph = (teamId: string) => `/api/teams/${encodeURIComponent(teamId)}/graph`

export const api = {
  getCatalog: () => request<CatalogResponse>('GET', '/api/catalog'),
  getDefaultGraph: () => request<Graph>('GET', '/api/graphs/default'),
  validateGraph: (graph: Graph) => request<ValidationReport>('POST', '/api/graphs/validate', graph),

  createSession: (facilitatorCode: string) =>
    request<CreateSessionResponse>('POST', '/api/sessions', { facilitatorCode }),
  joinTeam: (sessionCode: string, teamName: string) =>
    request<JoinTeamResponse>('POST', `/api/sessions/${code(sessionCode)}/teams`, { teamName }),
  getSession: (sessionCode: string) =>
    request<SessionDetail>('GET', `/api/sessions/${code(sessionCode)}`, undefined, 'facilitator'),
  lockSession: (sessionCode: string, locked: boolean) =>
    request<SessionDetail>('POST', `/api/sessions/${code(sessionCode)}/lock`, { locked }, 'facilitator'),

  getTeamGraph: (teamId: string) => request<StoredGraph>('GET', teamGraph(teamId), undefined, 'team'),
  /** 409 (stale version) carries the current StoredGraph as ApiError.body; 423 when locked. */
  saveTeamGraph: (teamId: string, version: number, graph: Graph, options?: { keepalive?: boolean }) =>
    request<StoredGraph>('PUT', teamGraph(teamId), { version, graph } satisfies SaveGraphRequest, 'team', options),
  resetTeamGraph: (teamId: string) => request<StoredGraph>('POST', `${teamGraph(teamId)}/reset`, undefined, 'team'),

  getPack: (packId: string) => request<PackSummary>('GET', `/api/packs/${encodeURIComponent(packId)}`),
  /** Runs the team's stored graph on the practice pack: 422 carries the ValidationReport, 409 a run is playing, 423 locked. */
  startPracticeRun: (teamId: string) =>
    request<RunRecord>('POST', `/api/teams/${encodeURIComponent(teamId)}/runs`, undefined, 'team'),
  stopRun: (runId: string, role: Role) =>
    request<RunRecord>('POST', `/api/runs/${encodeURIComponent(runId)}/stop`, undefined, role),
}
