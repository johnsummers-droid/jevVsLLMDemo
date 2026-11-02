// The session leaderboard (T21 ranking, T24): one row per team's latest official run. `large` is
// the shared-screen size. The score leads because it decides the order: it shows its sign, since
// below zero is a result worth seeing. A run with no numbers yet takes one short cell, not five dashes.
import { formatMs, formatPct, formatUsd } from '../lib/format'
import type { LeaderboardRow } from '../types'

const STATUS_LABELS: Record<string, string> = {
  running: 'running…',
  pending: 'preparing…',
  stopped: 'stopped',
  failed: 'graph has errors',
}
const METRIC_COLUMNS = 4

function formatScore(score: number): string {
  const rounded = Math.round(score)
  if (rounded === 0) return '0'
  return rounded > 0 ? `+${rounded}` : `−${-rounded}`
}

function Status({ status }: { status: string }) {
  return <span className={`leaderboard__status leaderboard__status--${status}`}>{STATUS_LABELS[status] ?? status}</span>
}

export function Leaderboard({ rows, large = false }: { rows: LeaderboardRow[]; large?: boolean }) {
  if (rows.length === 0) return <p className="page__hint">No official run yet.</p>
  return (
    <table className={`leaderboard${large ? ' leaderboard--large' : ''}`}>
      <thead>
        <tr>
          <th className="leaderboard__rank">#</th>
          <th>Team</th>
          <th className="leaderboard__num">Score</th>
          <th className="leaderboard__num">p95 latency</th>
          <th className="leaderboard__num">Cost / 1k</th>
          <th className="leaderboard__num">Automation</th>
          <th className="leaderboard__num">Unsafe</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const m = row.metrics
          const finished = row.status === 'completed'
          const classes = [
            'leaderboard__row',
            `leaderboard__row--${row.status}`,
            finished && row.rank === 1 && 'leaderboard__row--first',
          ]
          return (
            <tr key={row.teamId} className={classes.filter(Boolean).join(' ')}>
              <td className="leaderboard__rank">{finished ? row.rank : '–'}</td>
              <td className="leaderboard__team">
                {row.teamName}
                {!finished && m && <Status status={row.status} />}
              </td>
              {m ? (
                <>
                  <td className={`leaderboard__num leaderboard__score${(m.score ?? 0) < -0.5 ? ' leaderboard__score--negative' : ''}`}>
                    {formatScore(m.score ?? 0)}
                  </td>
                  <td className="leaderboard__num">{formatMs(m.p95LatencyMs)}</td>
                  <td className="leaderboard__num">{formatUsd(m.costPer1KUsd)}</td>
                  <td className="leaderboard__num">{formatPct(m.automationRate)}</td>
                  <td className={`leaderboard__num ${m.unsafeReleaseRate > 0 ? 'leaderboard__unsafe' : 'leaderboard__safe'}`}>
                    {formatPct(m.unsafeReleaseRate)}
                  </td>
                </>
              ) : (
                <td className="leaderboard__num" colSpan={METRIC_COLUMNS + 1}>
                  <Status status={row.status} />
                </td>
              )}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
