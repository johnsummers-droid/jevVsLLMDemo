// Number formatting for run telemetry (badges, metrics bar).

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)} s` : `${Math.round(ms)} ms`
}

export function formatUsd(usd: number): string {
  if (usd === 0) return '$0'
  if (usd < 0.01) return '<$0.01'
  return usd >= 100 ? `$${Math.round(usd).toLocaleString('en-US')}` : `$${usd.toFixed(2)}`
}

export function formatPct(rate: number): string {
  return `${Math.round(rate * 100)}%`
}
