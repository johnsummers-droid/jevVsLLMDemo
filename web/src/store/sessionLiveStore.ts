// The facilitator's live view of the session (plan1.txt T24, decision Q3): each team's current or
// last run (started, live metrics, ended) and the leaderboard, from the facilitator socket. The
// facilitator never gets the per-node firehose, so there is nothing to deduplicate here.
import { useEffect } from 'react'
import { create } from 'zustand'
import { api, signOutTo } from '../api/client'
import { type LiveStatus, openLive } from '../api/ws'
import type { LeaderboardRow, RunMetrics, RunMode, RunStatus, ServerEvent } from '../types'
import { useSessionStore } from './sessionStore'

export interface TeamRun {
  runId: string
  mode: RunMode
  status: RunStatus
  metrics: RunMetrics | null
}

export interface SessionLive {
  teamRuns: Record<string, TeamRun>
  leaderboard: LeaderboardRow[] | null
}

export const EMPTY_SESSION: SessionLive = { teamRuns: {}, leaderboard: null }

export function reduceSession(view: SessionLive, event: ServerEvent): SessionLive {
  if (event.type === 'leaderboard_updated') return { ...view, leaderboard: event.rows }
  const teamId = 'teamId' in event ? event.teamId : null
  if (!teamId) return view
  const current = view.teamRuns[teamId]
  const put = (run: TeamRun) => ({ ...view, teamRuns: { ...view.teamRuns, [teamId]: run } })
  switch (event.type) {
    case 'run_started':
      return put({ runId: event.runId ?? '', mode: event.config.mode, status: 'running', metrics: null })
    case 'metrics_snapshot':
      return current && current.runId === event.runId ? put({ ...current, metrics: event.metrics }) : view
    case 'run_completed':
      return current && current.runId === event.runId ? put({ ...current, status: event.status, metrics: event.metrics }) : view
    default:
      return view
  }
}

/** True while any team's official run plays. */
export const officialRunning = (view: SessionLive): boolean =>
  Object.values(view.teamRuns).some((run) => run.mode === 'official' && run.status === 'running')

interface SessionLiveState extends SessionLive {
  connection: LiveStatus
  apply: (event: ServerEvent) => void
  setLeaderboard: (rows: LeaderboardRow[]) => void
  reset: () => void
}

export const useSessionLiveStore = create<SessionLiveState>()((set, get) => ({
  ...EMPTY_SESSION,
  connection: 'offline',
  apply: (event) => {
    const view = get()
    const next = reduceSession(view, event)
    if (next !== view) set(next)
  },
  setLeaderboard: (leaderboard) => set({ leaderboard }),
  reset: () => set({ ...EMPTY_SESSION, connection: 'offline' }),
}))

/** Opens the facilitator's live stream; returns a function that closes it. */
export function startSessionLive(): () => void {
  const facilitator = useSessionStore.getState().facilitator
  if (!facilitator) return () => {}
  useSessionLiveStore.getState().reset()
  const stop = openLive({
    token: facilitator.token,
    onEvent: (event) => useSessionLiveStore.getState().apply(event),
    onStatus: (connection) => useSessionLiveStore.setState({ connection }),
    onAuthRejected: () => signOutTo('facilitator'),
  })
  return () => {
    stop()
    useSessionLiveStore.getState().reset()
  }
}

/** For the facilitator pages: opens the stream and (re)loads the leaderboard whenever it goes live. */
export function useSessionLive(sessionCode: string): void {
  const connection = useSessionLiveStore((s) => s.connection)
  useEffect(() => startSessionLive(), [sessionCode])
  useEffect(() => {
    if (connection !== 'live') return
    api.getLeaderboard(sessionCode).then(
      (rows) => useSessionLiveStore.getState().setLeaderboard(rows),
      () => {}, // the next leaderboard_updated brings it
    )
  }, [connection, sessionCode])
}
