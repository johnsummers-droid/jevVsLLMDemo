// /team: the workbench (palette, canvas, inspector) on the signed-in team's stored graph, saved
// automatically (saveStore). While the facilitator has locked graphs it is read-only.
import { ReactFlowProvider, useReactFlow } from '@xyflow/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Canvas } from '../canvas/Canvas'
import { Inspector } from '../inspector/Inspector'
import { navigate, PATHS } from '../lib/navigation'
import { Palette } from '../palette/Palette'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { type SaveStatus, startAutosave, useSaveStore } from '../store/saveStore'
import { type TeamCredentials, useSessionStore } from '../store/sessionStore'
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
  const signOut = useSessionStore((s) => s.signOut)
  const { screenToFlowPosition } = useReactFlow()
  const canvasRef = useRef<HTMLDivElement>(null)
  const { load: loadCatalog, status: catalogStatus } = catalog
  const { teamId } = team

  useEffect(() => {
    void loadCatalog()
  }, [loadCatalog])

  useEffect(() => startAutoValidation(), [])

  useEffect(() => startAutosave(), [])

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
      <main className="app__body">
        <Palette nodes={catalog.nodes} onAdd={addAtCenter} disabled={locked} />
        <div className="app__canvas" ref={canvasRef}>
          {graphStatus === 'ready' && <Canvas />}
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
