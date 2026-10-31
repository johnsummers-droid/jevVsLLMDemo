// Run traffic / Stop for the team's practice runs (T23, decision Q6) with the run's progress.
// Run is disabled, with the reason shown, while the graph is locked, the live stream is not
// connected (the run's events would be missed), or the pipeline check has errors. Unsaved edits
// are saved first: the server runs the stored graph.
import { useState } from 'react'
import { ApiError, api } from '../api/client'
import { countBySeverity } from '../lib/issues'
import { useGraphStore } from '../store/graphStore'
import { useRunPlaying, useRunStore } from '../store/runStore'
import { useSaveStore } from '../store/saveStore'
import { useValidationStore } from '../store/validationStore'
import type { ValidationReport } from '../types'

const STATUS_LABELS: Record<string, string> = {
  pending: 'Starting…',
  running: 'Running',
  completed: 'Finished',
  stopped: 'Stopped',
  failed: 'Failed',
}

function startError(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Could not reach the server.'
  if (error.status === 422) {
    const errors = countBySeverity((error.body as ValidationReport).issues).error
    return `The saved graph has ${errors} error${errors === 1 ? '' : 's'}; fix them first.`
  }
  if (error.status === 409) return 'A run is already in progress.'
  if (error.status === 423) return 'Graphs are locked.'
  return `Could not start the run (${error.status}).`
}

export function RunControls({ teamId }: { teamId: string }) {
  const run = useRunStore((s) => s.run)
  const playing = useRunPlaying()
  const connection = useRunStore((s) => s.connection)
  const done = useRunStore((s) => s.requestsDone)
  const total = useRunStore((s) => s.metrics?.total)
  const locked = useGraphStore((s) => s.locked)
  const reference = useGraphStore((s) => s.reference)
  const report = useValidationStore((s) => s.report)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const errors = report ? countBySeverity(report.issues).error : 0
  const blocked = locked
    ? 'Graphs are locked.'
    : reference !== null
      ? 'Viewing a reference graph: pick "User defined" to run your own.'
      : connection !== 'live'
      ? 'Connecting to live updates…'
      : errors > 0
        ? `Fix ${errors} error${errors === 1 ? '' : 's'} first (see Pipeline check).`
        : null

  const start = async () => {
    setBusy(true)
    setError(null)
    try {
      await useSaveStore.getState().flush()
      await api.startPracticeRun(teamId) // the run's events arrive over the live stream
    } catch (e) {
      if (e instanceof ApiError && e.status === 423) useGraphStore.getState().setLocked(true)
      setError(startError(e))
    } finally {
      setBusy(false)
    }
  }

  const stop = async () => {
    if (!run) return
    setBusy(true)
    try {
      await api.stopRun(run.runId, 'team')
    } catch {
      setError('Could not stop the run.')
    } finally {
      setBusy(false)
    }
  }

  const official = run?.config.mode === 'official'
  return (
    <div className="run-controls">
      {playing && !official ? (
        <button type="button" className="button button--danger" onClick={() => void stop()} disabled={busy}>
          Stop
        </button>
      ) : (
        <button
          type="button"
          className="button button--primary"
          onClick={() => void start()}
          disabled={busy || playing || blocked !== null}
          title={blocked ?? undefined}
        >
          {busy ? 'Starting…' : 'Run traffic'}
        </button>
      )}
      {run && (
        <span className="run-controls__progress" role="status">
          {official && <strong className="run-controls__official">Official run</strong>}
          {STATUS_LABELS[run.status] ?? run.status} · {done} / {total ?? '…'} requests
        </span>
      )}
      {!playing && blocked && <span className="run-controls__hint">{blocked}</span>}
      {error && (
        <span className="run-controls__error" role="alert">
          {error}
        </span>
      )}
    </div>
  )
}
