// The facilitator's official run (T24, decision Q7): start it (after a confirm: it locks every
// graph), see it playing, stop it for every team.
import { useState } from 'react'
import { ApiError, api } from '../api/client'
import { officialPreparing, officialRunning, useSessionLiveStore } from '../store/sessionLiveStore'

interface Props {
  sessionCode: string
  teamCount: number
  /** Called once a run started (the session is now locked). */
  onStarted: () => void
}

export function OfficialRunPanel({ sessionCode, teamCount, onStarted }: Props) {
  const running = useSessionLiveStore(officialRunning)
  const preparing = useSessionLiveStore(officialPreparing)
  const teamRuns = useSessionLiveStore((s) => s.teamRuns)
  const connection = useSessionLiveStore((s) => s.connection)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const start = async () => {
    setConfirming(false)
    setBusy(true)
    setError(null)
    try {
      const started = await api.startOfficialRun(sessionCode)
      const failed = started.runs.filter((r) => r.status === 'failed').length
      setMessage(
        `Started for ${started.runs.length} team${started.runs.length === 1 ? '' : 's'} (seed ${started.seed}).` +
          (failed ? ` ${failed} graph${failed === 1 ? ' has' : 's have'} errors and ranked last.` : ''),
      )
      onStarted()
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? 'An official run is already in progress.'
          : e instanceof ApiError
            ? `Starting failed (${e.status}).`
            : 'Could not reach the server.',
      )
    } finally {
      setBusy(false)
    }
  }

  const stopAll = async () => {
    setBusy(true)
    const playing = Object.values(teamRuns).filter(
      (r) => r.mode === 'official' && (r.status === 'running' || r.status === 'pending'),
    )
    const results = await Promise.allSettled(playing.map((r) => api.stopRun(r.runId, 'facilitator')))
    setError(results.some((r) => r.status === 'rejected') ? 'Some runs could not be stopped; try again.' : null)
    setBusy(false)
  }

  return (
    <section className="page__card">
      <div className="page__row">
        <h2>Official run</h2>
        <span className={`live-dot live-dot--${connection}`} title={`Live updates: ${connection}`} />
        {running ? (
          <>
            <strong className="official__running" role="status">
              {preparing ? 'Preparing…' : 'Playing…'}
            </strong>
            <button type="button" className="button button--danger" onClick={() => void stopAll()} disabled={busy}>
              Stop all
            </button>
          </>
        ) : confirming ? (
          <span className="app__confirm">
            Lock every graph and run all teams on the hidden pack?
            <button type="button" className="button button--small button--primary" onClick={() => void start()}>
              Start
            </button>
            <button type="button" className="button button--small" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </span>
        ) : (
          <button
            type="button"
            className="button button--primary"
            onClick={() => setConfirming(true)}
            disabled={busy || teamCount === 0}
          >
            {busy ? 'Starting…' : 'Start official run'}
          </button>
        )}
      </div>
      <p className="page__hint">
        Every team runs its saved graph on the same hidden tickets with the same seed; graphs are locked first.
      </p>
      {message && <p className="page__hint">{message}</p>}
      {error && (
        <p className="page__error" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
