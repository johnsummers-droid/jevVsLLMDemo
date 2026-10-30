import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeWebSocket } from '../test/fakeSocket'
import type { ServerEvent } from '../types'
import {
  CHECK_MS,
  type LiveStatus,
  liveUrl,
  openLive,
  PING_MS,
  RECONNECT_BASE_MS,
  RECONNECT_MAX_MS,
  SILENCE_MS,
} from './ws'

const SYNC = { type: 'state_sync', seq: 0, simMs: 0, locked: false }

function setup() {
  const events: ServerEvent[] = []
  const statuses: LiveStatus[] = []
  const rejected: number[] = []
  const stop = openLive({
    token: 'tok',
    url: 'ws://test/api/ws',
    onEvent: (e) => events.push(e),
    onStatus: (s) => statuses.push(s),
    onAuthRejected: (code) => rejected.push(code),
  })
  return { events, statuses, rejected, stop }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('liveUrl (Q9)', () => {
  it('derives wss from the API base URL', () => {
    expect(liveUrl('https://api.example.com', { protocol: 'https:', host: 'web.example.com' })).toBe(
      'wss://api.example.com/api/ws',
    )
    expect(liveUrl('http://localhost:8000/', { protocol: 'http:', host: 'x' })).toBe('ws://localhost:8000/api/ws')
  })

  it('uses the page origin when no base URL is set (Vite proxy)', () => {
    expect(liveUrl('', { protocol: 'http:', host: 'localhost:5173' })).toBe('ws://localhost:5173/api/ws')
    expect(liveUrl('', { protocol: 'https:', host: 'app.example.com' })).toBe('wss://app.example.com/api/ws')
  })
})

describe('openLive', () => {
  it('authenticates with its first message and goes live on state_sync', () => {
    const { events, statuses, stop } = setup()
    const ws = FakeWebSocket.latest()
    expect(ws.url).toBe('ws://test/api/ws')
    expect(statuses).toEqual(['connecting'])
    ws.open()
    expect(ws.sent).toEqual([{ type: 'auth', token: 'tok' }])
    ws.receive(SYNC)
    expect(statuses[statuses.length - 1]).toBe('live')
    expect(events).toEqual([SYNC])
    stop()
    expect(ws.closed).toBe(true)
    expect(statuses[statuses.length - 1]).toBe('offline')
  })

  it('pings every PING_MS and keeps pongs to itself', () => {
    const { events } = setup()
    const ws = FakeWebSocket.latest()
    ws.open()
    ws.receive(SYNC)
    vi.advanceTimersByTime(PING_MS)
    expect(ws.sent.filter((m) => (m as { type: string }).type === 'ping')).toHaveLength(1)
    ws.receive({ type: 'pong', seq: 0, simMs: 0 })
    expect(events).toHaveLength(1) // only state_sync
  })

  it('reconnects after SILENCE_MS without any message (a swallowed server restart)', () => {
    const { statuses } = setup()
    const first = FakeWebSocket.latest()
    first.open()
    first.receive(SYNC)
    vi.advanceTimersByTime(SILENCE_MS + CHECK_MS)
    expect(first.closed).toBe(true)
    expect(statuses[statuses.length - 1]).toBe('offline')
    vi.advanceTimersByTime(RECONNECT_BASE_MS)
    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('stays connected while pongs keep arriving', () => {
    setup()
    const ws = FakeWebSocket.latest()
    ws.open()
    ws.receive(SYNC)
    for (let i = 0; i < 6; i++) {
      vi.advanceTimersByTime(PING_MS)
      ws.receive({ type: 'pong', seq: 0, simMs: 0 })
    }
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(ws.closed).toBe(false)
  })

  it('backs off between attempts up to RECONNECT_MAX_MS, and resets once live', () => {
    setup()
    const delays: number[] = []
    for (let attempt = 0; attempt < 6; attempt++) {
      const count = FakeWebSocket.instances.length
      FakeWebSocket.latest().drop()
      let waited = 0
      while (FakeWebSocket.instances.length === count) {
        vi.advanceTimersByTime(250)
        waited += 250
      }
      delays.push(waited)
    }
    expect(delays).toEqual([1000, 2000, 4000, 8000, RECONNECT_MAX_MS, RECONNECT_MAX_MS])
    const ws = FakeWebSocket.latest()
    ws.open()
    ws.receive(SYNC)
    ws.drop()
    vi.advanceTimersByTime(RECONNECT_BASE_MS)
    expect(FakeWebSocket.instances).toHaveLength(8)
  })

  it.each([4401, 4403])('stops for good on closing %i and reports it', (code) => {
    const { rejected, statuses } = setup()
    const ws = FakeWebSocket.latest()
    ws.open()
    ws.receive({ type: 'closing', seq: 0, simMs: 0, code, reason: 'no' })
    expect(rejected).toEqual([code])
    expect(ws.closed).toBe(true)
    expect(statuses[statuses.length - 1]).toBe('offline')
    vi.advanceTimersByTime(RECONNECT_MAX_MS * 2)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it.each([1013, 1011])('reconnects on closing %i', (code) => {
    const { rejected } = setup()
    const ws = FakeWebSocket.latest()
    ws.open()
    ws.receive({ type: 'closing', seq: 0, simMs: 0, code, reason: 'later' })
    expect(ws.closed).toBe(true)
    vi.advanceTimersByTime(RECONNECT_BASE_MS)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(rejected).toEqual([])
  })

  it('does not reconnect after stop', () => {
    const { stop } = setup()
    stop()
    FakeWebSocket.latest().drop()
    vi.advanceTimersByTime(RECONNECT_MAX_MS)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })
})
