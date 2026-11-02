// TEMPORARY: /leaderboard-temp, for iterating on the leaderboard's design without an official run.
// It renders the real Leaderboard with made-up rows, in the same places as the live app, so a
// design change here is a change there. No sign-in and no server calls. Delete this file, its entry
// in PATHS, its line in App.tsx and its test before the workshop.
import { Leaderboard } from '../leaderboard/Leaderboard'
import type { LeaderboardRow, RunMetrics } from '../types'

function metrics(score: number, automation: number, escalation: number, unsafe: number, p95: number, cost: number, quality: number): RunMetrics {
  return {
    total: 30,
    completed: 30,
    automationRate: automation,
    escalationRate: escalation,
    unsafeReleaseRate: unsafe,
    droppedRate: 0,
    p50LatencyMs: p95 * 0.6,
    p95LatencyMs: p95,
    costPer1KUsd: cost,
    decisionQuality: quality,
    score,
  }
}

function row(rank: number, teamName: string, status: LeaderboardRow['status'], m?: RunMetrics): LeaderboardRow {
  return { teamId: `team-${rank}`, teamName, runId: `run-${rank}`, status, rank, metrics: m }
}

// A full session: 12 teams, spread like real results, and every state a row can be in.
const SAMPLE_ROWS: LeaderboardRow[] = [
  row(1, 'Copper Foxes', 'completed', metrics(97, 0.57, 0.43, 0, 2000, 867, 0.8)),
  row(2, 'Night Shift', 'completed', metrics(84, 0.6, 0.4, 0, 2300, 812, 0.77)),
  row(3, 'The Routers', 'completed', metrics(61, 0.67, 0.3, 0.03, 2150, 620, 0.73)),
  row(4, 'Team Warsaw', 'completed', metrics(38, 0.7, 0.27, 0.03, 2600, 548, 0.7)),
  row(5, 'Prompt Engineers', 'completed', metrics(25, 0.77, 0.17, 0.03, 12000, 335, 0.37)),
  row(6, 'Human in the Loop', 'completed', metrics(4, 0.2, 0.8, 0, 1900, 1610, 0.53)),
  row(7, 'Blue Herons', 'completed', metrics(-20, 0.73, 0, 0.1, 15700, 4, 0.33)),
  row(8, 'Escalate Everything', 'completed', metrics(-30, 0, 1, 0, 0, 2000, 0.4)),
  row(9, 'A Team With a Rather Long Name Indeed', 'stopped'),
  row(10, 'Late Starters', 'running'),
  row(11, 'Still Warming Up', 'pending'),
  row(12, 'Broken Graph', 'failed'),
]

export function LeaderboardTempPage() {
  return (
    <div className="screen">
      <p className="page__hint">Temporary design page with made-up teams and numbers.</p>
      <section className="screen__board">
        <h2>Leaderboard</h2>
        <Leaderboard rows={SAMPLE_ROWS} large />
      </section>
      <section className="screen__board">
        <h2>Facilitator page size</h2>
        <Leaderboard rows={SAMPLE_ROWS} />
      </section>
      <section className="screen__board">
        <h2>Before the official run</h2>
        <Leaderboard rows={[]} />
      </section>
    </div>
  )
}
