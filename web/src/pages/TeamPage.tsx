// /team: the workbench (palette, canvas, inspector) on the signed-in team's stored graph.
import { ReactFlowProvider, useReactFlow } from '@xyflow/react'
import { useCallback, useEffect, useRef } from 'react'
import { Canvas } from '../canvas/Canvas'
import { Inspector } from '../inspector/Inspector'
import { navigate, PATHS } from '../lib/navigation'
import { Palette } from '../palette/Palette'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { type TeamCredentials, useSessionStore } from '../store/sessionStore'
import { startAutoValidation } from '../store/validationStore'

function Workbench({ team }: { team: TeamCredentials }) {
  const catalog = useCatalogStore()
  const graphStatus = useGraphStore((s) => s.status)
  const graphError = useGraphStore((s) => s.error)
  const loadTeamGraph = useGraphStore((s) => s.loadTeamGraph)
  const addNode = useGraphStore((s) => s.addNode)
  const signOut = useSessionStore((s) => s.signOut)
  const { screenToFlowPosition } = useReactFlow()
  const canvasRef = useRef<HTMLDivElement>(null)
  const { load: loadCatalog, status: catalogStatus } = catalog
  const { teamId } = team

  useEffect(() => {
    void loadCatalog()
  }, [loadCatalog])

  useEffect(() => startAutoValidation(), [])

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

  const leave = () => {
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
          {error ? `Could not reach the server: ${error}` : graphStatus === 'ready' ? '' : 'Loading…'}
        </span>
        <span className="app__team">
          <strong>{team.teamName}</strong> · session {team.sessionCode}
        </span>
        <button type="button" className="button button--small" onClick={leave}>
          Sign out
        </button>
      </header>
      <main className="app__body">
        <Palette nodes={catalog.nodes} onAdd={addAtCenter} />
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
