// Live run state from the event stream (plan1.txt T22, decision Q4). `reduceRun` is pure: it
// rebuilds the server's per-node numbers from the events alone (node_completed and node_failed
// carry latency, cost, tokens, decisions and escalations), takes run metrics and skipped counts
// from metrics_snapshot, and ignores any event whose seq is not above the last one applied, so a
// reconnect's replay never double-counts. state_sync replaces everything: mid-run it is followed
// by a replay of the run so far; a finished run comes with its totals.
import { create } from 'zustand'
import { signOutTo } from '../api/client'
import { type LiveStatus, openLive } from '../api/ws'
import type { LeaderboardRow, NodeStats, RunMetrics, RunSummary, ServerEvent } from '../types'
import { useGraphStore } from './graphStore'
import { type Role, useSessionStore } from './sessionStore'

/** Edges waiting to be animated, oldest first; the canvas drains them (T23). */
export interface Pulse {
  edgeId: string
  requestId: string
  seq: number
}

export const MAX_PULSES = 500

export interface RunView {
  run: RunSummary | null
  /** The last seq applied for `run`; older or repeated events are ignored. */
  seq: number
  metrics: RunMetrics | null
  nodeStats: Record<string, NodeStats>
  edgeCounts: Record<string, number>
  requestsDone: number
  pulses: Pulse[]
}

export const EMPTY_RUN: RunView = {
  run: null,
  seq: 0,
  metrics: null,
  nodeStats: {},
  edgeCounts: {},
  requestsDone: 0,
  pulses: [],
}

const emptyStats = (nodeId: string): NodeStats => ({
  nodeId,
  requests: 0,
  skipped: 0,
  errors: 0,
  escalations: 0,
  avgLatencyMs: 0,
  totalCostUsd: 0,
  tokensOut: 0,
  decisions: {},
})

function countRun(
  view: RunView,
  nodeId: string,
  { latencyMs = 0, costUsd = 0, tokensOut = 0, escalated = false, failed = false, branch = null as string | null },
): RunView {
  const s = view.nodeStats[nodeId] ?? emptyStats(nodeId)
  const requests = s.requests + 1
  const decisions = branch ? { ...s.decisions, [branch]: (s.decisions?.[branch] ?? 0) + 1 } : s.decisions
  const next: NodeStats = {
    ...s,
    requests,
    errors: s.errors + (failed ? 1 : 0),
    escalations: s.escalations + (escalated ? 1 : 0),
    avgLatencyMs: (s.avgLatencyMs * s.requests + latencyMs) / requests,
    totalCostUsd: s.totalCostUsd + costUsd,
    tokensOut: s.tokensOut + tokensOut,
    decisions,
  }
  return { ...view, nodeStats: { ...view.nodeStats, [nodeId]: next } }
}

/** Applies one event to the run view. Events of other runs, and old seqs, change nothing. */
export function reduceRun(view: RunView, event: ServerEvent): RunView {
  if (event.type === 'state_sync') {
    const run = event.run ?? null
    if (run === null) return EMPTY_RUN
    const finished = run.status !== 'running' && run.status !== 'pending'
    // Mid-run the replay that follows rebuilds the numbers; a finished run comes with its totals.
    const nodeStats = finished ? Object.fromEntries((event.nodeStats ?? []).map((s) => [s.nodeId, s])) : {}
    return { ...EMPTY_RUN, run, seq: event.seq, metrics: event.metrics ?? null, nodeStats }
  }
  if (event.type === 'run_started') {
    const run: RunSummary = {
      runId: event.runId ?? '',
      teamId: event.teamId,
      status: 'running',
      config: event.config,
      graphVersion: event.graphVersion ?? 0,
    }
    return { ...EMPTY_RUN, run, seq: event.seq }
  }
  if (!('runId' in event) || !view.run || event.runId !== view.run.runId || event.seq <= view.seq) return view
  const view2: RunView = { ...view, seq: event.seq }
  switch (event.type) {
    case 'node_completed':
      return countRun(view2, event.nodeId, {
        latencyMs: event.latencyMs,
        costUsd: event.costUsd,
        tokensOut: event.tokensOut ?? 0,
        escalated: event.escalated ?? false,
        branch: event.firedBranch ?? null,
      })
    case 'node_failed':
      return countRun(view2, event.nodeId, { latencyMs: event.latencyMs, costUsd: event.costUsd, failed: true })
    case 'edge_transferred': {
      const pulses = [...view2.pulses, { edgeId: event.edgeId, requestId: event.requestId, seq: event.seq }]
      return {
        ...view2,
        edgeCounts: { ...view2.edgeCounts, [event.edgeId]: (view2.edgeCounts[event.edgeId] ?? 0) + 1 },
        pulses: pulses.length > MAX_PULSES ? pulses.slice(-MAX_PULSES) : pulses,
      }
    }
    case 'request_completed':
      return { ...view2, requestsDone: view2.requestsDone + 1 }
    case 'metrics_snapshot': {
      // Skipped nodes produce no events: their counts (and nodes that never ran) come from here.
      const nodeStats = { ...view2.nodeStats }
      for (const s of event.nodeStats) nodeStats[s.nodeId] = { ...(nodeStats[s.nodeId] ?? emptyStats(s.nodeId)), skipped: s.skipped }
      return { ...view2, metrics: event.metrics, nodeStats }
    }
    case 'run_completed':
      return { ...view2, run: { ...view2.run!, status: event.status }, metrics: event.metrics }
    default:
      return view2
  }
}

interface RunState extends RunView {
  connection: LiveStatus
  /** The session's leaderboard (facilitator sockets only). */
  leaderboard: LeaderboardRow[] | null
  apply: (event: ServerEvent) => void
  /** Takes the edges waiting to be animated. */
  drainPulses: () => Pulse[]
  reset: () => void
}

/** Lock state from the stream, for the team whose graph is loaded (Q5). */
function applyLock(teamId: string | null | undefined, locked: boolean | undefined): void {
  const graph = useGraphStore.getState()
  if (locked === undefined || !teamId || graph.teamId !== teamId || graph.locked === locked) return
  graph.setLocked(locked)
}

export const useRunStore = create<RunState>()((set, get) => ({
  ...EMPTY_RUN,
  connection: 'offline',
  leaderboard: null,
  apply: (event) => {
    if (event.type === 'graph_locked') return applyLock(event.teamId, event.locked)
    if (event.type === 'leaderboard_updated') return set({ leaderboard: event.rows })
    if (event.type === 'state_sync') applyLock(event.teamId, event.locked)
    const view = get()
    const next = reduceRun(view, event)
    if (next !== view) set(next)
  },
  drainPulses: () => {
    const { pulses } = get()
    if (pulses.length) set({ pulses: [] })
    return pulses
  },
  reset: () => set({ ...EMPTY_RUN, connection: 'offline', leaderboard: null }),
}))

/** Opens the live stream for a signed-in role; returns a function that closes it. */
export function startLive(role: Role): () => void {
  const credentials = useSessionStore.getState()[role]
  if (!credentials) return () => {}
  useRunStore.getState().reset()
  const stop = openLive({
    token: credentials.token,
    onEvent: (event) => useRunStore.getState().apply(event),
    onStatus: (connection) => useRunStore.setState({ connection }),
    onAuthRejected: () => signOutTo(role),
  })
  return () => {
    stop()
    useRunStore.getState().reset()
  }
}

/** True while the team's own run plays: the canvas stays read-only so the animation matches it (Q6). */
export function useRunPlaying(): boolean {
  return useRunStore((s) => s.run?.status === 'running' || s.run?.status === 'pending')
}

/** Editing is off while the graph is locked, a run plays, or a reference graph is on view. */
export function useReadOnly(): boolean {
  const locked = useGraphStore((s) => s.locked || s.reference !== null)
  return useRunPlaying() || locked
}
