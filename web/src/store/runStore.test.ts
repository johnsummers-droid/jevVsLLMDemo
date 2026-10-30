import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import fixture from '../../../shared/fixtures/run-events.json'
import { FakeWebSocket } from '../test/fakeSocket'
import type { NodeStats, RunMetrics, ServerEvent, StoredGraph } from '../types'
import { useGraphStore } from './graphStore'
import { EMPTY_RUN, MAX_PULSES, reduceRun, type RunView, startLive, useRunStore } from './runStore'
import { useSessionStore } from './sessionStore'

const EVENTS = fixture.events as ServerEvent[]
const FINAL_STATS = fixture.finalNodeStats as NodeStats[]
const FINAL_METRICS = fixture.finalMetrics as RunMetrics

const reduceAll = (events: ServerEvent[], from: RunView = EMPTY_RUN) => events.reduce(reduceRun, from)

function expectStatsToMatch(actual: Record<string, NodeStats>, expected: NodeStats[]) {
  expect(Object.keys(actual).sort()).toEqual(expected.map((s) => s.nodeId).sort())
  for (const want of expected) {
    const got = actual[want.nodeId]
    const { avgLatencyMs, totalCostUsd, ...exact } = want
    expect({ ...got, avgLatencyMs: 0, totalCostUsd: 0, decisions: got.decisions ?? {} }).toEqual({
      ...exact,
      avgLatencyMs: 0,
      totalCostUsd: 0,
      decisions: exact.decisions ?? {},
    })
    expect(got.avgLatencyMs).toBeCloseTo(avgLatencyMs, 6)
    expect(got.totalCostUsd).toBeCloseTo(totalCostUsd, 9)
  }
}

describe('reduceRun', () => {
  it("rebuilds the server's final node stats and metrics from the events alone", () => {
    const view = reduceAll(EVENTS)
    expect(view.run?.runId).toBe('fixture-run')
    expect(view.run?.status).toBe('completed')
    expect(view.metrics).toEqual(FINAL_METRICS)
    expectStatsToMatch(view.nodeStats, FINAL_STATS)
    expect(view.requestsDone).toBe(FINAL_METRICS.total)
    const transfers = EVENTS.filter((e) => e.type === 'edge_transferred').length
    expect(Object.values(view.edgeCounts).reduce((a, b) => a + b, 0)).toBe(transfers)
    expect(view.seq).toBe(EVENTS[EVENTS.length - 1]!.seq)
  })

  it('ignores duplicates and old seqs, so a replay never double-counts', () => {
    const half = Math.floor(EVENTS.length / 2)
    const twice = reduceAll([...EVENTS.slice(0, half), ...EVENTS.slice(1, half), ...EVENTS.slice(half), ...EVENTS])
    expect(twice.nodeStats).toEqual(reduceAll(EVENTS).nodeStats)
    expect(twice.requestsDone).toBe(FINAL_METRICS.total)
  })

  it('ignores events of another run', () => {
    const view = reduceAll(EVENTS.slice(0, 50))
    const stranger = { ...EVENTS[60], runId: 'other-run', seq: 10_000 } as ServerEvent
    expect(reduceRun(view, stranger)).toBe(view)
  })

  it('a mid-run state_sync followed by the replay ends where a connected client is', () => {
    const cut = 120
    const sync = {
      type: 'state_sync',
      seq: 0,
      simMs: 0,
      runId: 'fixture-run',
      teamId: 'fixture-team',
      run: { runId: 'fixture-run', teamId: 'fixture-team', status: 'running', config: (EVENTS[0] as { config: object }).config },
      nodeStats: [{ ...FINAL_STATS[0], requests: 999 }], // ignored mid-run: the replay rebuilds
      locked: false,
    } as ServerEvent
    const reconnected = reduceAll([...EVENTS.slice(1, cut), ...EVENTS.slice(cut)], reduceRun(reduceAll(EVENTS.slice(0, 40)), sync))
    expect(reconnected.nodeStats).toEqual(reduceAll(EVENTS).nodeStats)
    expect(reconnected.metrics).toEqual(FINAL_METRICS)
  })

  it('a finished run is taken from the state_sync totals', () => {
    const last = EVENTS[EVENTS.length - 1]!
    const sync = {
      type: 'state_sync',
      seq: last.seq,
      simMs: last.simMs,
      runId: 'fixture-run',
      run: { runId: 'fixture-run', status: 'completed', config: (EVENTS[0] as { config: object }).config },
      metrics: FINAL_METRICS,
      nodeStats: FINAL_STATS,
    } as ServerEvent
    const view = reduceRun(EMPTY_RUN, sync)
    expect(view.metrics).toEqual(FINAL_METRICS)
    expectStatsToMatch(view.nodeStats, FINAL_STATS)
    expect(reduceRun(view, last)).toBe(view) // nothing after it is applied twice
    expect(reduceRun(view, { type: 'state_sync', seq: 0, simMs: 0, run: null } as ServerEvent)).toBe(EMPTY_RUN)
  })

  it('a new run_started starts from zero', () => {
    const view = reduceAll(EVENTS)
    const next = reduceRun(view, { ...(EVENTS[0] as object), runId: 'second', seq: 0 } as ServerEvent)
    expect(next.run?.runId).toBe('second')
    expect(next.nodeStats).toEqual({})
    expect(next.requestsDone).toBe(0)
  })

  it('counts a failed node call with its latency and cost', () => {
    const view = reduceAll(EVENTS.slice(0, 1))
    const failed = {
      type: 'node_failed',
      runId: 'fixture-run',
      seq: 1,
      simMs: 5,
      requestId: 'r1',
      nodeId: 'llm',
      error: { code: 'timeout', message: 'slow', retryable: true },
      latencyMs: 2000,
      costUsd: 0.01,
    } as ServerEvent
    const s = reduceRun(view, failed).nodeStats.llm
    expect(s).toMatchObject({ requests: 1, errors: 1, avgLatencyMs: 2000, totalCostUsd: 0.01 })
  })

  it('queues edge pulses for the canvas, capped at MAX_PULSES', () => {
    const view = reduceAll(EVENTS)
    const transfers = EVENTS.filter((e) => e.type === 'edge_transferred')
    expect(view.pulses).toHaveLength(Math.min(transfers.length, MAX_PULSES))
    expect(view.pulses[view.pulses.length - 1]!.seq).toBe(transfers[transfers.length - 1]!.seq)
  })
})

describe('useRunStore and startLive', () => {
  const stored: StoredGraph = {
    teamId: 't1',
    version: 3,
    locked: false,
    graph: { schemaVersion: 1, nodes: [], edges: [] },
    updatedAt: '2026-10-30T12:00:00Z',
  }

  beforeEach(() => {
    useRunStore.getState().reset()
    useGraphStore.getState().clear()
    useSessionStore.setState({ team: { sessionCode: 'ABC234', teamId: 't1', teamName: 'Red', token: 'tok' }, facilitator: null })
  })

  afterEach(() => useSessionStore.setState({ team: null, facilitator: null }))

  it('drains pulses once', () => {
    EVENTS.slice(0, 80).forEach((e) => useRunStore.getState().apply(e))
    const first = useRunStore.getState().drainPulses()
    expect(first.length).toBeGreaterThan(0)
    expect(useRunStore.getState().drainPulses()).toEqual([])
  })

  it('applies graph_locked and the state_sync lock to the loaded team graph only', () => {
    useGraphStore.getState().setStoredGraph(stored)
    const apply = useRunStore.getState().apply
    apply({ type: 'graph_locked', seq: 0, simMs: 0, teamId: 'other', locked: true })
    expect(useGraphStore.getState().locked).toBe(false)
    apply({ type: 'graph_locked', seq: 0, simMs: 0, teamId: 't1', locked: true })
    expect(useGraphStore.getState().locked).toBe(true)
    apply({ type: 'state_sync', seq: 0, simMs: 0, teamId: 't1', locked: false })
    expect(useGraphStore.getState().locked).toBe(false)
  })

  it('keeps the leaderboard', () => {
    const rows = [{ teamId: 't1', teamName: 'Red', runId: 'r', status: 'running' as const, rank: 1 }]
    useRunStore.getState().apply({ type: 'leaderboard_updated', seq: 0, simMs: 0, rows })
    expect(useRunStore.getState().leaderboard).toEqual(rows)
  })

  it('startLive opens the socket with the role token, tracks the connection and resets on stop', () => {
    const stop = startLive('team')
    const ws = FakeWebSocket.latest()
    expect(useRunStore.getState().connection).toBe('connecting')
    ws.open()
    expect(ws.sent[0]).toEqual({ type: 'auth', token: 'tok' })
    ws.receive({ type: 'state_sync', seq: 0, simMs: 0, teamId: 't1', locked: false })
    expect(useRunStore.getState().connection).toBe('live')
    EVENTS.slice(0, 30).forEach((e) => ws.receive(e))
    expect(useRunStore.getState().run?.runId).toBe('fixture-run')
    stop()
    expect(useRunStore.getState().connection).toBe('offline')
    expect(useRunStore.getState().run).toBeNull()
  })

  it('a refused token signs the role out', () => {
    startLive('team')
    const ws = FakeWebSocket.latest()
    ws.open()
    ws.receive({ type: 'closing', seq: 0, simMs: 0, code: 4403, reason: 'joined again' })
    expect(useSessionStore.getState().team).toBeNull()
  })

  it('does nothing without credentials', () => {
    useSessionStore.setState({ team: null, facilitator: null })
    startLive('team')()
    expect(FakeWebSocket.instances).toHaveLength(0)
  })
})
