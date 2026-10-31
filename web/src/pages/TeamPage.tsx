// /team: the workbench (palette, canvas, inspector) on the signed-in team's stored graph, saved
// automatically (saveStore), with Run traffic, live telemetry and the run's metrics (T23). While the
// facilitator has locked graphs, or a run plays, it is read-only.
import { ReactFlowProvider, useReactFlow } from '@xyflow/react'
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { Canvas } from '../canvas/Canvas'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { HelpPanel } from '../help/HelpPanel'
import { Inspector } from '../inspector/Inspector'
import { navigate, PATHS } from '../lib/navigation'
import { Palette } from '../palette/Palette'
import { MetricsBar } from '../run/MetricsBar'
import { RunControls } from '../run/RunControls'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { useHelpStore } from '../store/helpStore'
import { type SaveStatus, startAutosave, useSaveStore } from '../store/saveStore'
import { type TeamCredentials, useSessionStore } from '../store/sessionStore'
import { startLive, useReadOnly } from '../store/runStore'
import { startAutoValidation } from '../store/validationStore'

const SAVE_LABELS: Record<SaveStatus, string> = {
  saved: 'Saved',
  pending: 'Saving…',
  saving: 'Saving…',
  offline: 'Offline – retrying',
  locked: 'Locked',
  error: 'Not saved',
}

function SaveIndicator() {
  const status = useSaveStore((s) => s.status)
  const error = useSaveStore((s) => s.error)
  return (
    <span className={`save-status save-status--${status}`} role="status" title={error ?? undefined}>
      {SAVE_LABELS[status]}
    </span>
  )
}

function ResetButton({ disabled }: { disabled: boolean }) {
  const reset = useSaveStore((s) => s.reset)
  const [confirming, setConfirming] = useState(false)
  if (!confirming) {
    return (
      <button type="button" className="button button--small" disabled={disabled} onClick={() => setConfirming(true)}>
        Reset graph
      </button>
    )
  }
  return (
    <span className="app__confirm">
      Replace your graph with the default graph?
      <button
        type="button"
        className="button button--small button--danger"
        onClick={() => {
          setConfirming(false)
          void reset()
        }}
      >
        Reset
      </button>
      <button type="button" className="button button--small" onClick={() => setConfirming(false)}>
        Cancel
      </button>
    </span>
  )
}

function Workbench({ team }: { team: TeamCredentials }) {
  const catalog = useCatalogStore()
  const graphStatus = useGraphStore((s) => s.status)
  const graphError = useGraphStore((s) => s.error)
  const loadTeamGraph = useGraphStore((s) => s.loadTeamGraph)
  const addNode = useGraphStore((s) => s.addNode)
  const locked = useGraphStore((s) => s.locked)
  const readOnly = useReadOnly()
  const signOut = useSessionStore((s) => s.signOut)
  const { screenToFlowPosition } = useReactFlow()
  const canvasRef = useRef<HTMLDivElement>(null)
  const helpOpen = useHelpStore((s) => s.nodeType !== null)
  const helpHeight = useHelpStore((s) => s.height)
  const { load: loadCatalog, status: catalogStatus } = catalog
  const { teamId } = team

  useEffect(() => {
    void loadCatalog()
  }, [loadCatalog])

  useEffect(() => startAutoValidation(), [])

  useEffect(() => startAutosave(), [])

  // The help panel belongs to this page; leaving it closes the panel.
  useEffect(() => () => useHelpStore.getState().close(), [])

  // The live event stream: locks now, run events from T23 on.
  useEffect(() => startLive('team'), [teamId])

  // Never show another team's graph: start empty whenever the team changes.
  useEffect(() => {
    useGraphStore.getState().clear()
  }, [teamId])

  // The graph's node components need the catalog, so the team's graph loads after it.
  useEffect(() => {
    if (catalogStatus === 'ready' && graphStatus === 'empty') void loadTeamGraph(teamId)
  }, [catalogStatus, graphStatus, loadTeamGraph, teamId])

  const addAtCenter = useCallback(
    (nodeType: string) => {
      const rect = canvasRef.current?.getBoundingClientRect()
      const center = rect ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 } : { x: 0, y: 0 }
      addNode(nodeType, screenToFlowPosition(center))
    },
    [addNode, screenToFlowPosition],
  )

  const leave = async () => {
    await useSaveStore.getState().flush()
    signOut('team')
    useGraphStore.getState().clear()
    navigate(PATHS.join)
  }

  const error = catalog.error ?? graphError
  return (
    <div className="app">
      <header className="app__header">
        <h1>Pipeline Simulator</h1>
        <span className="app__status">
          {error ? `Could not reach the server: ${error}` : graphStatus === 'ready' ? <SaveIndicator /> : 'Loading…'}
        </span>
        {graphStatus === 'ready' && <ResetButton disabled={locked} />}
        <span className="app__team">
          <strong>{team.teamName}</strong> · session {team.sessionCode}
        </span>
        <button type="button" className="button button--small" onClick={() => void leave()}>
          Sign out
        </button>
      </header>
      {locked && (
        <div className="app__banner" role="alert">
          Pencils down: the facilitator has locked the graphs. You can look around, but not edit.
        </div>
      )}
      {graphStatus === 'ready' && (
        <ErrorBoundary name="the run bar">
          <div className="run-bar">
            <RunControls teamId={teamId} />
            <MetricsBar />
          </div>
        </ErrorBoundary>
      )}
      <main className="app__body">
        <Palette nodes={catalog.nodes} onAdd={addAtCenter} disabled={readOnly} />
        <div
          className={`app__canvas${helpOpen ? ' app__canvas--help-open' : ''}`}
          ref={canvasRef}
          style={{ '--help-height': `${helpHeight * 100}%` } as CSSProperties}
        >
          {graphStatus === 'ready' && (
            <ErrorBoundary name="the canvas">
              <Canvas />
            </ErrorBoundary>
          )}
          <ErrorBoundary name="the help panel">
            <HelpPanel />
          </ErrorBoundary>
        </div>
        <Inspector />
      </main>
    </div>
  )
}

export function TeamPage({ team }: { team: TeamCredentials }) {
  return (
    <ReactFlowProvider>
      <Workbench team={team} />
    </ReactFlowProvider>
  )
}
