import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readCredentials, STORAGE_KEY, useSessionStore } from './sessionStore'

const team = { sessionCode: 'ABC234', teamId: 't1', teamName: 'Red', token: 'team-token' }
const facilitator = { sessionCode: 'ABC234', token: 'fac-token' }

beforeEach(() => {
  window.localStorage.clear()
  useSessionStore.setState({ team: null, facilitator: null })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('sessionStore', () => {
  it('stores credentials and reads them back after a reload', () => {
    useSessionStore.getState().setTeam(team)
    useSessionStore.getState().setFacilitator(facilitator)
    expect(readCredentials()).toEqual({ team, facilitator })
  })

  it('signs out one role and drops the key when nothing is left', () => {
    useSessionStore.getState().setTeam(team)
    useSessionStore.getState().setFacilitator(facilitator)
    useSessionStore.getState().signOut('team')
    expect(readCredentials()).toEqual({ team: null, facilitator })
    useSessionStore.getState().signOut('facilitator')
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('ignores malformed stored data', () => {
    window.localStorage.setItem(STORAGE_KEY, '{not json')
    expect(readCredentials()).toEqual({ team: null, facilitator: null })
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ team: { teamId: 't1' }, facilitator: { token: 3 } }))
    expect(readCredentials()).toEqual({ team: null, facilitator: null })
  })

  it('works in memory when storage throws', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    useSessionStore.getState().setTeam(team)
    expect(useSessionStore.getState().team).toEqual(team)
    expect(readCredentials()).toEqual({ team: null, facilitator: null })
  })
})
