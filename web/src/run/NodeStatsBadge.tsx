// Per-node run telemetry under a node (T23): requests, average latency and cost, then whatever
// this node did: branch decisions, tokens, escalations, errors and skips. Shown once the team has
// a run (live or finished); the numbers come from runStore.
import { formatMs, formatUsd } from '../lib/format'
import { useGraphStore } from '../store/graphStore'
import { useRunStore } from '../store/runStore'

const MAX_DECISIONS = 3

/** "route.billing" -> "billing": branch ports are named after their decision. */
const branchLabel = (branch: string) => branch.slice(branch.indexOf('.') + 1)

export function NodeStatsBadge({ nodeId }: { nodeId: string }) {
  const hasRun = useRunStore((s) => s.run !== null)
  const stats = useRunStore((s) => s.nodeStats[nodeId])
  // A reference graph has the same node ids, but the team's numbers aren't its numbers.
  const viewingReference = useGraphStore((s) => s.reference !== null)
  if (!hasRun || viewingReference) return null
  if (!stats || (stats.requests === 0 && stats.skipped === 0)) {
    return (
      <div className="node-stats node-stats--idle" aria-label="Run statistics">
        no traffic yet
      </div>
    )
  }
  const decisions = Object.entries(stats.decisions ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, MAX_DECISIONS)
  return (
    <div className="node-stats" aria-label="Run statistics">
      <div className="node-stats__main">
        <span title="Requests this node handled">{stats.requests} req</span>
        {stats.requests > 0 && <span title="Average latency">{formatMs(stats.avgLatencyMs)}</span>}
        {stats.totalCostUsd > 0 && <span title="Total cost">{formatUsd(stats.totalCostUsd)}</span>}
      </div>
      {(decisions.length > 0 || stats.tokensOut > 0 || stats.escalations > 0 || stats.errors > 0 || stats.skipped > 0) && (
        <div className="node-stats__extra">
          {decisions.map(([branch, count]) => (
            <span key={branch} title={`Requests routed to ${branch}`}>
              {branchLabel(branch)} {count}
            </span>
          ))}
          {stats.tokensOut > 0 && <span title="Generated tokens">{stats.tokensOut.toLocaleString('en-US')} tok</span>}
          {stats.escalations > 0 && (
            <span className="node-stats__escalated" title="Sent to human review">
              {stats.escalations} escalated
            </span>
          )}
          {stats.errors > 0 && (
            <span className="node-stats__error" title="Failed calls">
              {stats.errors} failed
            </span>
          )}
          {stats.skipped > 0 && <span title="Requests that took another branch">{stats.skipped} skipped</span>}
        </div>
      )}
    </div>
  )
}
