// Team and facilitator credentials. Kept in localStorage so a refresh stays signed in; every
// storage access is guarded, so the app still works (signed in until reload) without it.
import { create } from 'zustand'

export interface TeamCredentials {
  sessionCode: string
  teamId: string
  teamName: string
  token: string
}

export interface FacilitatorCredentials {
  sessionCode: string
  token: string
}

export type Role = 'team' | 'facilitator'

interface Credentials {
  team: TeamCredentials | null
  facilitator: FacilitatorCredentials | null
}

interface SessionState extends Credentials {
  setTeam: (team: TeamCredentials) => void
  setFacilitator: (facilitator: FacilitatorCredentials) => void
  /** Forgets one role's credentials (sign-out, or a 401 from the server). */
  signOut: (role: Role) => void
}

export const STORAGE_KEY = 'pipeline-sim.credentials'

const isString = (value: unknown): value is string => typeof value === 'string' && value !== ''

function parseTeam(value: unknown): TeamCredentials | null {
  const v = value as Partial<TeamCredentials> | null
  return v && isString(v.sessionCode) && isString(v.teamId) && isString(v.teamName) && isString(v.token)
    ? { sessionCode: v.sessionCode, teamId: v.teamId, teamName: v.teamName, token: v.token }
    : null
}

function parseFacilitator(value: unknown): FacilitatorCredentials | null {
  const v = value as Partial<FacilitatorCredentials> | null
  return v && isString(v.sessionCode) && isString(v.token) ? { sessionCode: v.sessionCode, token: v.token } : null
}

export function readCredentials(): Credentials {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    const data = raw ? (JSON.parse(raw) as Partial<Credentials>) : {}
    return { team: parseTeam(data.team), facilitator: parseFacilitator(data.facilitator) }
  } catch {
    return { team: null, facilitator: null }
  }
}

function writeCredentials({ team, facilitator }: Credentials): void {
  try {
    if (team || facilitator) window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ team, facilitator }))
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Storage blocked or full: the credentials live in memory only.
  }
}

export const useSessionStore = create<SessionState>()((set, get) => {
  const update = (patch: Partial<Credentials>) => {
    set(patch)
    writeCredentials({ team: get().team, facilitator: get().facilitator })
  }
  return {
    ...readCredentials(),
    setTeam: (team) => update({ team }),
    setFacilitator: (facilitator) => update({ facilitator }),
    signOut: (role) => update({ [role]: null }),
  }
})
