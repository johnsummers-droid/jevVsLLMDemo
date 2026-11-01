import { describe, expect, it } from 'vitest'
import { createAnimator, DOT_MS, DOT_RADIUS, MAX_DOTS_PER_EDGE, type PathLike } from './pulses'

const straight: PathLike = {
  getTotalLength: () => 100,
  getPointAtLength: (length) => ({ x: length, y: 0 }),
}

function layer(): SVGGElement {
  return document.createElementNS('http://www.w3.org/2000/svg', 'g')
}

const pulse = (edgeId: string, seq: number) => ({ edgeId, requestId: `r${seq}`, seq })

function manualFrames() {
  const pending: ((now: number) => void)[] = []
  return {
    request: (cb: (now: number) => void) => pending.push(cb),
    run: (now: number) => pending.splice(0).forEach((cb) => cb(now)),
    pending: () => pending.length,
  }
}

describe('pulse animator', () => {
  it('draws dots at the large radius, with the class that makes them throb', () => {
    const animator = createAnimator(() => 0)
    const g = layer()
    animator.track('e1', straight, g)
    animator.push([pulse('e1', 1)])
    animator.frame(0)
    const dot = g.querySelector('circle')!
    expect(dot.getAttribute('r')).toBe(DOT_RADIUS)
    expect(Number(DOT_RADIUS)).toBeGreaterThan(4)
    expect(dot.getAttribute('class')).toBe('pulse-dot')
  })

  it('moves a dot along the path and removes it after DOT_MS', () => {
    const animator = createAnimator(() => 0)
    const g = layer()
    animator.track('e1', straight, g)
    animator.push([pulse('e1', 1)])
    expect(animator.frame(0)).toBe(true)
    const dot = g.querySelector('circle')!
    expect(dot.getAttribute('cx')).toBe('0')
    animator.frame(DOT_MS / 2)
    expect(Number(dot.getAttribute('cx'))).toBeCloseTo(50)
    expect(animator.frame(DOT_MS)).toBe(false)
    expect(g.querySelector('circle')).toBeNull()
  })

  it('caps the dots per edge so a spike stays smooth', () => {
    const animator = createAnimator(() => 0)
    animator.track('e1', straight, layer())
    animator.push(Array.from({ length: 50 }, (_, i) => pulse('e1', i)))
    animator.frame(0)
    expect(animator.dotCount('e1')).toBe(MAX_DOTS_PER_EDGE)
  })

  it('ignores pulses for edges it does not track, and drains its source each frame', () => {
    let source = [pulse('e1', 1), pulse('gone', 2)]
    const animator = createAnimator(() => 0, () => source.splice(0))
    animator.track('e1', straight, layer())
    animator.frame(0)
    expect(animator.dotCount('e1')).toBe(1)
    expect(source).toEqual([])
    source = []
  })

  it('runs its loop only while there is something to animate', () => {
    const frames = manualFrames()
    const animator = createAnimator(frames.request)
    animator.track('e1', straight, layer())
    animator.wake()
    animator.wake() // already scheduled
    expect(frames.pending()).toBe(1)
    frames.run(0)
    expect(frames.pending()).toBe(0) // nothing to do: the loop stopped
    animator.push([pulse('e1', 1)])
    frames.run(0)
    frames.run(DOT_MS / 2)
    expect(frames.pending()).toBe(1)
    frames.run(DOT_MS)
    expect(frames.pending()).toBe(0)
  })

  it('unregistering an edge removes its dots', () => {
    const animator = createAnimator(() => 0)
    const g = layer()
    const untrack = animator.track('e1', straight, g)
    animator.push([pulse('e1', 1)])
    animator.frame(0)
    untrack()
    expect(g.querySelector('circle')).toBeNull()
    expect(animator.dotCount('e1')).toBe(0)
  })

  it('a path that cannot be measured leaves the dot at its start instead of failing', () => {
    const animator = createAnimator(() => 0)
    const broken: PathLike = { getTotalLength: () => { throw new Error('not laid out') }, getPointAtLength: () => ({ x: 0, y: 0 }) }
    animator.track('e1', broken, layer())
    animator.push([pulse('e1', 1)])
    expect(() => animator.frame(0)).not.toThrow()
    expect(animator.dotCount('e1')).toBe(1)
  })
})
