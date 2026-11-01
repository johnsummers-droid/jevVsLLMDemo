// The session leaderboard (T21 ranking, T24): one row per team's latest official run. `large` is
// the shared-screen size.
import { formatMs, formatPct, formatUsd } from '../lib/format'
import type { LeaderboardRow } from '../types'

const STATUS_LABELS: Record<string, string> = {
  running: 'running…',
  pending: 'preparing…',
  stopped: 'stopped',
  failed: 'graph has errors',
}

export function Leaderboard({ rows, large = false }: { rows: LeaderboardRow[]; large?: boolean }) {
  if (rows.length === 0) return <p className="page__hint">No official run yet.</p>
  return (
    <table className={`leaderboard${large ? ' leaderboard--large' : ''}`}>
      <thead>
        <tr>
          <th>#</th>
          <th>Team</th>
          <th>Score</th>
          <th>p95 latency</th>
          <th>Cost / 1k</th>
          <th>Automation</th>
          <th>Unsafe</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const m = row.metrics
          return (
            <tr key={row.teamId} className={`leaderboard__row leaderboard__row--${row.status}`}>
              <td>{row.status === 'completed' ? row.rank : '–'}</td>
              <td>
                {row.teamName}
                {row.status !== 'completed' && <span className="leaderboard__status"> {STATUS_LABELS[row.status] ?? row.status}</span>}
              </td>
              <td className="leaderboard__score">{m ? (m.score ?? 0).toFixed(0) : '—'}</td>
              <td>{m ? formatMs(m.p95LatencyMs) : '—'}</td>
              <td>{m ? formatUsd(m.costPer1KUsd) : '—'}</td>
              <td>{m ? formatPct(m.automationRate) : '—'}</td>
              <td className={m && m.unsafeReleaseRate > 0 ? 'leaderboard__unsafe' : undefined}>
                {m ? formatPct(m.unsafeReleaseRate) : '—'}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
