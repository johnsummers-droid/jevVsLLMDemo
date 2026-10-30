// Request dots along edges (plan1.txt T23). One requestAnimationFrame loop for the whole canvas:
// each frame it drains the edge transfers runStore queued, starts a dot per transfer (at most
// MAX_DOTS_PER_EDGE per edge, so a traffic spike stays smooth; the count is still exact in the
// run store) and moves every dot along its edge's path by setting attributes directly, with no
// React render. It runs only while there is something to animate.
import { type Pulse, useRunStore } from '../store/runStore'

export const DOT_MS = 700
export const MAX_DOTS_PER_EDGE = 6
const DOT_RADIUS = '4'
const SVG_NS = 'http://www.w3.org/2000/svg'

/** The part of an SVG path element the animator uses (a fake in tests). */
export interface PathLike {
  getTotalLength(): number
  getPointAtLength(length: number): { x: number; y: number }
}

interface Track {
  path: PathLike
  layer: Element
  dots: { start: number; element: Element }[]
}

export interface Animator {
  /** Registers an edge's path and the layer its dots go into; returns the unregister function. */
  track: (edgeId: string, path: PathLike, layer: Element) => () => void
  /** Queues pulses and makes sure the loop runs. */
  push: (pulses: Pulse[]) => void
  /** Makes sure the loop runs (it drains the run store on its next frame). */
  wake: () => void
  /** One frame (exposed for tests). Returns whether another frame is needed. */
  frame: (now: number) => boolean
  dotCount: (edgeId: string) => number
}

export function createAnimator(
  requestFrame: (callback: (now: number) => void) => unknown = (cb) => requestAnimationFrame(cb),
  drain: () => Pulse[] = () => [],
): Animator {
  const tracks = new Map<string, Track>()
  let queued: Pulse[] = []
  let running = false

  const frame = (now: number): boolean => {
    const pulses = queued.concat(drain())
    queued = []
    for (const pulse of pulses) {
      const track = tracks.get(pulse.edgeId)
      if (!track || track.dots.length >= MAX_DOTS_PER_EDGE) continue
      const element = track.layer.ownerDocument.createElementNS(SVG_NS, 'circle')
      element.setAttribute('r', DOT_RADIUS)
      element.setAttribute('class', 'pulse-dot')
      track.layer.appendChild(element)
      track.dots.push({ start: now, element })
    }
    let busy = false
    for (const track of tracks.values()) {
      let length = 0
      try {
        length = track.path.getTotalLength()
      } catch {
        // a path not laid out yet (or jsdom): the dot waits at the start
      }
      track.dots = track.dots.filter(({ start, element }) => {
        const progress = (now - start) / DOT_MS
        if (progress >= 1) {
          element.remove()
          return false
        }
        if (length > 0) {
          const point = track.path.getPointAtLength(Math.max(0, progress) * length)
          element.setAttribute('cx', String(point.x))
          element.setAttribute('cy', String(point.y))
        }
        return true
      })
      busy ||= track.dots.length > 0
    }
    return busy || queued.length > 0
  }

  const loop = (now: number) => {
    if (frame(now)) requestFrame(loop)
    else running = false
  }

  const wake = () => {
    if (running) return
    running = true
    requestFrame(loop)
  }

  return {
    track: (edgeId, path, layer) => {
      tracks.set(edgeId, { path, layer, dots: [] })
      return () => {
        const track = tracks.get(edgeId)
        track?.dots.forEach(({ element }) => element.remove())
        if (track?.path === path) tracks.delete(edgeId)
      }
    },
    push: (pulses) => {
      queued = queued.concat(pulses)
      wake()
    },
    wake,
    frame,
    dotCount: (edgeId) => tracks.get(edgeId)?.dots.length ?? 0,
  }
}

/** The canvas's animator, fed from the run store whenever pulses arrive. */
export const animator = createAnimator(undefined, () => useRunStore.getState().drainPulses())

/** Starts feeding the animator from the run store; returns a function that stops it. */
export function startPulses(): () => void {
  return useRunStore.subscribe((state, previous) => {
    if (state.pulses.length && state.pulses !== previous.pulses) animator.wake()
  })
}
