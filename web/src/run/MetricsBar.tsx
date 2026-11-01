// The four MVP metrics of the team's current or last run (spec section 11, T23), each against the
// mission target from the pack's scoring: p95 latency and cost per 1,000 within budget, no unsafe
// releases. Automation rate has no target (higher is better). The score shows once the run ends.
import { useEffect } from 'react'
import { formatMs, formatPct, formatUsd } from '../lib/format'
import { usePackStore } from '../store/packStore'
import { useRunStore } from '../store/runStore'

type Verdict = 'pass' | 'fail' | 'neutral'

interface Tile {
  label: string
  value: string
  target?: string
  verdict: Verdict
}

function MetricTile({ label, value, target, verdict }: Tile) {
  return (
    <div className={`metric metric--${verdict}`} role="group" aria-label={label}>
      <span className="metric__label">{label}</span>
      <span className="metric__value">{value}</span>
      {target && <span className="metric__target">{target}</span>}
    </div>
  )
}

export function MetricsBar() {
  const run = useRunStore((s) => s.run)
  const metrics = useRunStore((s) => s.metrics)
  const packId = run?.config.packId
  const scoring = usePackStore((s) => (packId ? s.packs[packId]?.scoring : undefined))
  const loadPack = usePackStore((s) => s.load)

  useEffect(() => {
    if (packId) void loadPack(packId)
  }, [packId, loadPack])

  if (!run) return null
  const latencyBudget = scoring ? (scoring.latencyBudgetMs ?? 2500) : undefined // the server's default
  // Nothing is judged until requests have completed; a run's first metrics arrive after it starts.
  const m = metrics !== null && metrics.completed > 0 ? metrics : null
  const judge = (ok: boolean | undefined): Verdict => (ok === undefined ? 'neutral' : ok ? 'pass' : 'fail')
  const tiles: Tile[] = [
    {
      label: 'p95 latency',
      value: m ? formatMs(m.p95LatencyMs) : '—',
      target: latencyBudget === undefined ? undefined : `target ≤ ${formatMs(latencyBudget)}`,
      verdict: judge(m && latencyBudget !== undefined ? m.p95LatencyMs <= latencyBudget : undefined),
    },
    {
      label: 'Cost per 1,000',
      value: m ? formatUsd(m.costPer1KUsd) : '—',
      target: scoring && `budget ${formatUsd(scoring.costBudgetPer1KUsd)}`,
      verdict: judge(m && scoring ? m.costPer1KUsd <= scoring.costBudgetPer1KUsd : undefined),
    },
    {
      label: 'Automation',
      value: m ? formatPct(m.automationRate) : '—',
      target: 'higher is better',
      verdict: 'neutral',
    },
    {
      label: 'Unsafe releases',
      value: m ? formatPct(m.unsafeReleaseRate) : '—',
      target: 'target 0%',
      verdict: judge(m ? m.unsafeReleaseRate === 0 : undefined),
    },
  ]
  const finished = run.status === 'completed' || run.status === 'stopped'
  return (
    <div className="metrics-bar" aria-label="Run metrics">
      {tiles.map((tile) => (
        <MetricTile key={tile.label} {...tile} />
      ))}
      {finished && metrics && (
        <MetricTile label="Score" value={(metrics.score ?? 0).toFixed(0)} target={run.status === 'stopped' ? 'partial run' : undefined} verdict="neutral" />
      )}
    </div>
  )
}
