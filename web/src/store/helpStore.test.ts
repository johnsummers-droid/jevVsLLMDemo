import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_HELP_HEIGHT, MAX_HELP_HEIGHT, MIN_HELP_HEIGHT, clampHelpHeight, useHelpStore } from './helpStore'

const initial = useHelpStore.getState()

beforeEach(() => {
  window.localStorage.clear()
  useHelpStore.setState(initial, true)
})

afterEach(() => vi.restoreAllMocks())

describe('helpStore', () => {
  it('shows one node type at a time: another swaps, the same one closes', () => {
    const { toggle } = useHelpStore.getState()
    toggle('policy_engine')
    expect(useHelpStore.getState().nodeType).toBe('policy_engine')
    toggle('jev_intent_router')
    expect(useHelpStore.getState().nodeType).toBe('jev_intent_router')
    toggle('jev_intent_router')
    expect(useHelpStore.getState().nodeType).toBeNull()
  })

  it('returns focus to the "?" that opened it', () => {
    const opener = document.createElement('button')
    document.body.append(opener)
    useHelpStore.getState().open('policy_engine', opener)
    useHelpStore.getState().close()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })

  it('clamps the height and remembers it', () => {
    expect(clampHelpHeight(2)).toBe(MAX_HELP_HEIGHT)
    expect(clampHelpHeight(0)).toBe(MIN_HELP_HEIGHT)
    useHelpStore.getState().setHeight(0.55)
    expect(useHelpStore.getState().height).toBe(0.55)
    expect(window.localStorage.getItem('pipeline-sim:help-height')).toBe('0.55')
    useHelpStore.getState().setHeight(5)
    expect(useHelpStore.getState().height).toBe(MAX_HELP_HEIGHT)
  })

  it('works when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    useHelpStore.getState().setHeight(0.5)
    expect(useHelpStore.getState().height).toBe(0.5)
    expect(initial.height).toBe(DEFAULT_HELP_HEIGHT)
  })
})
