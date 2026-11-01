// /screen: the shared screen for the room (plan1.txt T24, decision Q10). Signed in with the
// facilitator's stored credentials (open /facilitator in the same browser first): how to join,
// the leaderboard in large type, and one live metrics tile per team. No canvases.
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { Leaderboard } from '../leaderboard/Leaderboard'
import { formatMs, formatPct, formatUsd } from '../lib/format'
import { PATHS } from '../lib/navigation'
import { REFRESH_MS } from './FacilitatorPage'
import { type FacilitatorCredentials, useSessionStore } from '../store/sessionStore'
import { type TeamRun, useSessionLive, useSessionLiveStore } from '../store/sessionLiveStore'
import type { TeamSummary } from '../types'
import { Link } from './Link'

function TeamTile({ name, run }: { name: string; run: TeamRun | undefined }) {
  const m = run?.metrics
  const status = !run ? 'waiting' : run.status === 'running' ? `${run.mode} run playing` : run.status === 'pending' ? `${run.mode} run preparing` : `${run.mode} run ${run.status}`
  return (
    <div className={`screen-tile screen-tile--${run?.status ?? 'idle'}`} role="group" aria-label={name}>
      <strong className="screen-tile__name">{name}</strong>
      <span className="screen-tile__status">{status}</span>
      {m && m.completed > 0 && (
        <dl className="screen-tile__metrics">
          <dt>p95</dt>
          <dd>{formatMs(m.p95LatencyMs)}</dd>
          <dt>cost/1k</dt>
          <dd>{formatUsd(m.costPer1KUsd)}</dd>
          <dt>auto</dt>
          <dd>{formatPct(m.automationRate)}</dd>
          <dt>unsafe</dt>
          <dd className={m.unsafeReleaseRate > 0 ? 'screen-tile__unsafe' : undefined}>{formatPct(m.unsafeReleaseRate)}</dd>
        </dl>
      )}
    </div>
  )
}

function Screen({ facilitator }: { facilitator: FacilitatorCredentials }) {
  const { sessionCode } = facilitator
  const [teams, setTeams] = useState<TeamSummary[]>([])
  const teamRuns = useSessionLiveStore((s) => s.teamRuns)
  const leaderboard = useSessionLiveStore((s) => s.leaderboard)
  useSessionLive(sessionCode)

  useEffect(() => {
    const load = () => api.getSession(sessionCode).then((d) => setTeams(d.teams), () => {})
    void load()
    const timer = window.setInterval(() => void load(), REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [sessionCode])

  return (
    <div className="screen">
      <header className="screen__header">
        <h1>Pipeline Simulator</h1>
        <p>
          Join at <strong>{window.location.host}{PATHS.join}</strong> with code{' '}
          <strong className="screen__code">{sessionCode}</strong>
        </p>
      </header>
      <ErrorBoundary name="the leaderboard">
        <section className="screen__board">
          <h2>Leaderboard</h2>
          {leaderboard ? <Leaderboard rows={leaderboard} large /> : <p className="page__hint">Loading…</p>}
        </section>
      </ErrorBoundary>
      <ErrorBoundary name="the team tiles">
        <section className="screen__tiles" aria-label="Teams">
          {teams.map((team) => (
            <TeamTile key={team.teamId} name={team.name} run={teamRuns[team.teamId]} />
          ))}
        </section>
      </ErrorBoundary>
    </div>
  )
}

export function ScreenPage() {
  const facilitator = useSessionStore((s) => s.facilitator)
  if (!facilitator) {
    return (
      <div className="page">
        <section className="page__card">
          <h1>Shared screen</h1>
          <p>
            Open the <Link to={PATHS.facilitator}>facilitator page</Link> in this browser and create the session first;
            this screen uses its sign-in.
          </p>
        </section>
      </div>
    )
  }
  return <Screen key={facilitator.sessionCode} facilitator={facilitator} />
}
