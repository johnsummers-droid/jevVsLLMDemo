import { describe, expect, it } from 'vitest'
import type { RunMetrics, ServerEvent } from '../types'
import { EMPTY_SESSION, officialPreparing, officialRunning, reduceSession, type SessionLive } from './sessionLiveStore'

const metrics = (score: number): RunMetrics => ({
  total: 30, completed: 30, automationRate: 0.5, escalationRate: 0.2, unsafeReleaseRate: 0, droppedRate: 0,
  p50LatencyMs: 300, p95LatencyMs: 700, costPer1KUsd: 900, decisionQuality: 0.9, score,
})
const started = (teamId: string, runId: string, mode: 'practice' | 'official' = 'official') =>
  ({ type: 'run_started', runId, teamId, seq: 0, simMs: 0, config: { mode, packId: mode, seed: 7 } }) as ServerEvent
const reduce = (events: ServerEvent[], from: SessionLive = EMPTY_SESSION) => events.reduce(reduceSession, from)

describe('reduceSession', () => {
  it("follows each team's run from start to end", () => {
    const view = reduce([
      started('red', 'r1'),
      started('blue', 'b1', 'practice'),
      { type: 'metrics_snapshot', runId: 'r1', teamId: 'red', seq: 5, simMs: 1, metrics: metrics(10), nodeStats: [] },
      { type: 'run_completed', runId: 'b1', teamId: 'blue', seq: 9, simMs: 2, status: 'stopped', metrics: metrics(3) },
    ])
    expect(view.teamRuns.red).toMatchObject({ runId: 'r1', mode: 'official', status: 'running', metrics: metrics(10) })
    expect(view.teamRuns.blue).toMatchObject({ runId: 'b1', mode: 'practice', status: 'stopped', metrics: metrics(3) })
    expect(officialRunning(view)).toBe(true)
    const done = reduce([{ type: 'run_completed', runId: 'r1', teamId: 'red', seq: 20, simMs: 3, status: 'completed', metrics: metrics(50) }], view)
    expect(done.teamRuns.red.status).toBe('completed')
    expect(officialRunning(done)).toBe(false)
  })

  it("ignores another run's late events", () => {
    const view = reduce([started('red', 'r2')])
    const stale = { type: 'metrics_snapshot', runId: 'r1', teamId: 'red', seq: 5, simMs: 1, metrics: metrics(1), nodeStats: [] } as ServerEvent
    expect(reduceSession(view, stale)).toBe(view)
  })

  it('keeps the latest leaderboard', () => {
    const rows = [{ teamId: 'red', teamName: 'Red', runId: 'r1', status: 'running' as const, rank: 1 }]
    expect(reduce([{ type: 'leaderboard_updated', seq: 0, simMs: 0, rows }]).leaderboard).toEqual(rows)
  })

  it('official runs prepare, then play', () => {
    const config = { mode: 'official', packId: 'official', seed: 7 }
    const preparing = reduce([{ type: 'run_preparing', runId: 'r1', teamId: 'red', seq: 0, simMs: 0, config } as ServerEvent])
    expect(preparing.teamRuns.red.status).toBe('pending')
    expect(officialRunning(preparing)).toBe(true)
    expect(officialPreparing(preparing)).toBe(true)
    const playing = reduce([{ type: 'run_started', runId: 'r1', teamId: 'red', seq: 0, simMs: 0, config, warnings: ['simulated'] } as ServerEvent], preparing)
    expect(officialPreparing(playing)).toBe(false)
    expect(playing.teamRuns.red.warnings).toEqual(['simulated'])
  })
})
