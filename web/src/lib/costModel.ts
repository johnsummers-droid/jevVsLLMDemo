// A node's CostModel as label/value rows (Inspector and help panel).
import type { CostModel } from '../types'

const usd = (n: number) => `$${n < 0.01 && n > 0 ? n.toPrecision(2) : n.toFixed(2)}`

export function costRows(cost: CostModel): [string, string][] {
  const rows: [string, string][] = []
  const jitter = cost.latencyJitterMs ? ` ± ${cost.latencyJitterMs} ms` : ''
  const latency = cost.latencyMs >= 1000 ? `${cost.latencyMs / 1000} s` : `${cost.latencyMs} ms`
  rows.push(['Latency', `${latency}${jitter}`])
  if (cost.perTokenLatencyMs) rows.push(['Per output token', `+ ${cost.perTokenLatencyMs} ms`])
  rows.push(['Cost per call', usd(cost.costPerCallUsd ?? 0)])
  if (cost.priceInPer1KUsd != null) rows.push(['Input price', `${usd(cost.priceInPer1KUsd)} / 1k tokens`])
  if (cost.priceOutPer1KUsd != null) rows.push(['Output price', `${usd(cost.priceOutPer1KUsd)} / 1k tokens`])
  if (cost.excludedFromLatency) rows.push(['Latency metrics', 'not counted in p95 latency'])
  return rows
}
