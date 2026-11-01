// /team: the workbench (palette, canvas, inspector) on the signed-in team's stored graph, saved
// automatically (saveStore), with Run traffic, live telemetry and the run's metrics (T23). While the
// facilitator has locked graphs, or a run plays, it is read-only.
import { ReactFlowProvider, useReactFlow } from '@xyflow/react'
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { Canvas } from '../canvas/Canvas'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { LockIcon } from '../components/LockIcon'
import { Logo } from '../components/Logo'
import { PanelToggle } from '../components/PanelToggle'
import { HelpPanel } from '../help/HelpPanel'
import { Inspector } from '../inspector/Inspector'
import { navigate, PATHS } from '../lib/navigation'
import { Palette } from '../palette/Palette'
import { BUNDLED_REFERENCES, REFERENCE_GRAPHS, referenceViewerEnabled, viewReference, viewRevealed } from '../lib/referenceGraphs'
import { useReveal } from '../reference/useReveal'
import { ReferencePicker } from './ReferencePicker'
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
      {status === 'locked' && <LockIcon />}
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
  const reference = useGraphStore((s) => s.reference)
  const [showPicker] = useState(() => referenceViewerEnabled())
  const [paletteCollapsed, setPaletteCollapsed] = useState(false)
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false)
  const revealed = useReveal(team.teamId, locked)
  const readOnly = useReadOnly()
  const signOut = useSessionStore((s) => s.signOut)
  const { screenToFlowPosition } = useReactFlow()
  const canvasRef = useRef<HTMLDivElement>(null)
  const helpOpen = useHelpStore((s) => s.nodeType !== null)
  const helpHeight = useHelpStore((s) => s.height)
  const { load: loadCatalog, status: catalogStatus } = catalog
  const { teamId } = team

  // Unlocking ends the reveal: back to the team's own graph (?ref has its own "User defined").
  useEffect(() => {
    if (!showPicker && !locked && reference !== null) void viewReference(null)
  }, [showPicker, locked, reference])

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
        <h1 className="app__logo">
          <Logo />
        </h1>
        <span className="app__status">
          {error ? `Could not reach the server: ${error}` : graphStatus === 'ready' ? <SaveIndicator /> : 'Loading…'}
        </span>
        {graphStatus === 'ready' && <ResetButton disabled={locked || reference !== null} />}
        {graphStatus === 'ready' && showPicker && (
          <ReferencePicker label="Graph" graphs={BUNDLED_REFERENCES} onPick={viewReference} />
        )}
        {graphStatus === 'ready' && !showPicker && revealed.length > 0 && (
          <ReferencePicker label="View reference graph" graphs={revealed} onPick={viewRevealed} />
        )}
        <span className="app__team">
          <strong className="app__team-name" title={team.teamName}>
            {team.teamName}
          </strong>
          <span className="app__session">session {team.sessionCode}</span>
        </span>
        <button type="button" className="button button--small" onClick={() => void leave()}>
          Sign out
        </button>
      </header>
      {locked && (
        <div className="app__banner" role="alert">
          <LockIcon />
          Pencils down: the facilitator has locked the graphs. You can look around, but not edit.
        </div>
      )}
      {reference !== null && (
        <div className="app__banner app__banner--reference" role="status">
          Viewing the reference graph “{REFERENCE_GRAPHS[reference]?.label ?? reference}” (read-only, not
          saved). Pick “User defined” to go back to your graph.
        </div>
      )}
      <main className="app__body">
        {/* Hidden, not removed, so a panel keeps its state (open sections, half-typed values). */}
        <div className="app__side" hidden={paletteCollapsed}>
          <Palette nodes={catalog.nodes} onAdd={addAtCenter} disabled={readOnly} />
        </div>
        <div
          className={`app__canvas${helpOpen ? ' app__canvas--help-open' : ''}`}
          ref={canvasRef}
          style={{ '--help-height': `${helpHeight * 100}%` } as CSSProperties}
        >
          {graphStatus === 'ready' && (
            <ErrorBoundary name="the canvas">
              <Canvas key={reference ?? 'user'} />
            </ErrorBoundary>
          )}
          <PanelToggle side="left" name="node palette" collapsed={paletteCollapsed} onToggle={() => setPaletteCollapsed((c) => !c)} />
          <PanelToggle side="right" name="node information panel" collapsed={inspectorCollapsed} onToggle={() => setInspectorCollapsed((c) => !c)} />
          {locked && (
            <span className="app__canvas-lock">
              <LockIcon label="This graph is locked" />
            </span>
          )}
          <ErrorBoundary name="the help panel">
            <HelpPanel />
          </ErrorBoundary>
        </div>
        <div className="app__side" hidden={inspectorCollapsed}>
          <Inspector />
        </div>
      </main>
      {graphStatus === 'ready' && (
        <ErrorBoundary name="the run bar">
          <div className="run-bar">
            <MetricsBar />
            <RunControls teamId={teamId} />
          </div>
        </ErrorBoundary>
      )}
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
