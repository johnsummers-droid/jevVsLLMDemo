// /facilitator: the facilitator code creates a session (decision P2); then the session code is
// shown large for the room, the team list refreshes every few seconds, one button locks or
// unlocks every team graph ("pencils down"), and the official run, each team's run and the
// leaderboard follow the live stream (T24).
import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../api/client'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { Leaderboard } from '../leaderboard/Leaderboard'
import { PATHS } from '../lib/navigation'
import { ReferenceGraphView } from '../reference/ReferenceGraphView'
import { OfficialRunPanel } from '../run/OfficialRunPanel'
import { type FacilitatorCredentials, useSessionStore } from '../store/sessionStore'
import { type TeamRun, useSessionLive, useSessionLiveStore } from '../store/sessionLiveStore'
import type { SessionDetail } from '../types'
import { Logo } from '../components/Logo'
import { Link } from './Link'

const RUN_LABELS: Record<string, string> = {
  running: 'running',
  pending: 'preparing',
  completed: 'finished',
  stopped: 'stopped',
  failed: 'failed',
}

const runLabel = (run: TeamRun | undefined) =>
  run ? `${run.mode === 'official' ? 'Official' : 'Practice'} · ${RUN_LABELS[run.status] ?? run.status}` : '—'

export const REFRESH_MS = 5000

function createError(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Could not reach the server.'
  if (error.status === 401) return 'Wrong facilitator code.'
  if (error.status === 503) return 'The server has no FACILITATOR_CODE or TOKEN_SECRET set.'
  return `Creating the session failed (${error.status}).`
}

function CreateSession() {
  const setFacilitator = useSessionStore((s) => s.setFacilitator)
  const [facilitatorCode, setFacilitatorCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!facilitatorCode || busy) return
    setBusy(true)
    setError(null)
    try {
      const created = await api.createSession(facilitatorCode)
      setFacilitator({ sessionCode: created.sessionCode, token: created.facilitatorToken })
    } catch (e) {
      setError(createError(e))
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <Logo className="page__logo" />
      <form className="page__card" onSubmit={submit}>
        <h1>Start a workshop session</h1>
        <label className="field">
          <span>Facilitator code</span>
          <input
            className="field__input"
            type="password"
            value={facilitatorCode}
            onChange={(e) => setFacilitatorCode(e.target.value)}
            autoComplete="off"
          />
        </label>
        {error && (
          <p className="page__error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="button button--primary" disabled={!facilitatorCode || busy}>
          {busy ? 'Creating…' : 'Create session'}
        </button>
        <p className="page__footer">
          Joining as a team? <Link to={PATHS.join}>Join page</Link>
        </p>
      </form>
    </div>
  )
}

const timeFormat = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })

function SessionView({ facilitator }: { facilitator: FacilitatorCredentials }) {
  const signOut = useSessionStore((s) => s.signOut)
  const { sessionCode } = facilitator
  const [detail, setDetail] = useState<SessionDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmSignOut, setConfirmSignOut] = useState(false)
  const teamRuns = useSessionLiveStore((s) => s.teamRuns)
  const leaderboard = useSessionLiveStore((s) => s.leaderboard)
  useSessionLive(sessionCode)

  const refresh = useCallback(async () => {
    try {
      setDetail(await api.getSession(sessionCode))
      setError(null)
    } catch (e) {
      // A 401 signs the facilitator out in the client; anything else keeps the last list.
      setError(e instanceof ApiError ? `Refreshing failed (${e.status}).` : 'Could not reach the server.')
    }
  }, [sessionCode])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [refresh])

  const teams = detail?.teams ?? []
  // The session's flag (Q5): it also covers teams that join while graphs are locked.
  const locked = detail?.locked ?? false

  const toggleLock = async () => {
    setBusy(true)
    try {
      setDetail(await api.lockSession(sessionCode, !locked))
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError ? `Locking failed (${e.status}).` : 'Could not reach the server.')
    } finally {
      setBusy(false)
    }
  }

  const joinUrl = `${window.location.origin}${PATHS.join}?code=${sessionCode}`
  return (
    <div className="page page--wide">
      <Logo className="page__logo" />
      <section className="page__card">
        <p className="page__hint">Session code</p>
        <p className="session-code" aria-label="Session code">
          {sessionCode}
        </p>
        <p className="page__hint">
          Teams join at <code>{joinUrl}</code>
        </p>
      </section>

      <ErrorBoundary name="the official run panel">
        <OfficialRunPanel sessionCode={sessionCode} teamCount={teams.length} onStarted={() => void refresh()} />
      </ErrorBoundary>

      <section className="page__card">
        <div className="page__row">
          <h2>
            Teams <span className="page__count">{teams.length}</span>
          </h2>
          <button
            type="button"
            className={locked ? 'button' : 'button button--primary'}
            onClick={toggleLock}
            disabled={busy || detail === null}
          >
            {locked ? 'Unlock graphs' : 'Pencils down (lock graphs)'}
          </button>
        </div>
        {error && (
          <p className="page__error" role="alert">
            {error}
          </p>
        )}
        {teams.length === 0 ? (
          <p className="page__hint">{detail ? 'No teams yet.' : 'Loading…'}</p>
        ) : (
          <table className="team-table">
            <thead>
              <tr>
                <th>Team</th>
                <th>Joined</th>
                <th>Saves</th>
                <th>Graph</th>
                <th>Run</th>
              </tr>
            </thead>
            <tbody>
              {teams.map((team) => (
                <tr key={team.teamId}>
                  <td>{team.name}</td>
                  <td>{timeFormat.format(new Date(team.joinedAt))}</td>
                  <td>{team.graphVersion}</td>
                  <td>{team.locked ? 'Locked' : 'Editing'}</td>
                  <td>
                    {runLabel(teamRuns[team.teamId])}
                    {teamRuns[team.teamId]?.warnings?.map((warning) => (
                      <span key={warning} className="run-controls__error" role="alert">
                        {' '}
                        {warning}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="page__card">
        <div className="page__row">
          <h2>Leaderboard</h2>
          <a className="button button--small" href={PATHS.screen} target="_blank" rel="noreferrer">
            Open shared screen
          </a>
        </div>
        <ErrorBoundary name="the leaderboard">
          {leaderboard ? <Leaderboard rows={leaderboard} /> : <p className="page__hint">Loading…</p>}
        </ErrorBoundary>
      </section>

      <section className="page__card">
        <ErrorBoundary name="the reference graph">
          <ReferenceGraphView sessionCode={sessionCode} />
        </ErrorBoundary>
      </section>

      <section className="page__card">
        {confirmSignOut ? (
          <div className="page__row">
            <span>The session keeps running, but this browser loses facilitator access to it.</span>
            <button type="button" className="button" onClick={() => signOut('facilitator')}>
              Sign out
            </button>
            <button type="button" className="button" onClick={() => setConfirmSignOut(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <div className="page__row">
            <button type="button" className="button" onClick={() => setConfirmSignOut(true)}>
              Sign out
            </button>
          </div>
        )}
      </section>
    </div>
  )
}

export function FacilitatorPage() {
  const facilitator = useSessionStore((s) => s.facilitator)
  return facilitator ? <SessionView key={facilitator.sessionCode} facilitator={facilitator} /> : <CreateSession />
}
