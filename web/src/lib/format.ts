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

// A score between -1 and 1 keeps two decimals, so a real small score doesn't read as "no score".
export function formatRunScore(score: number): string {
  if (Math.abs(score) >= 1) return score.toFixed(0)
  const text = score.toFixed(2)
  return Number(text) === 0 ? '0.00' : text // toFixed keeps the sign: -0.001 would print "-0.00"
}
