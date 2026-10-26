import { afterEach, describe, expect, it, vi } from 'vitest'
import { navigate, pageFromPath } from './navigation'

afterEach(() => {
  window.history.replaceState(null, '', '/')
})

describe('navigation', () => {
  it('maps pathnames to pages', () => {
    expect(pageFromPath('/join')).toBe('join')
    expect(pageFromPath('/team/')).toBe('team')
    expect(pageFromPath('/facilitator')).toBe('facilitator')
    expect(pageFromPath('/')).toBeNull()
    expect(pageFromPath('/teams')).toBeNull()
  })

  it('pushes a history entry and fires popstate', () => {
    const onPop = vi.fn()
    window.addEventListener('popstate', onPop)
    const length = window.history.length
    navigate('/team')
    expect(window.location.pathname).toBe('/team')
    expect(window.history.length).toBe(length + 1)
    expect(onPop).toHaveBeenCalledTimes(1)
    navigate('/team')
    expect(onPop).toHaveBeenCalledTimes(1)
    navigate('/join', { replace: true })
    expect(window.history.length).toBe(length + 1)
    window.removeEventListener('popstate', onPop)
  })
})
