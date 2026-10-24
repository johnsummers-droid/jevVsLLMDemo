import { ReactFlowProvider, useReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useCallback, useEffect, useRef } from 'react'
import './App.css'
import { Canvas } from './canvas/Canvas'
import { Palette } from './palette/Palette'
import { useCatalogStore } from './store/catalogStore'
import { useGraphStore } from './store/graphStore'

function Workbench() {
  const catalog = useCatalogStore()
  const graphStatus = useGraphStore((s) => s.status)
  const graphError = useGraphStore((s) => s.error)
  const loadDefault = useGraphStore((s) => s.loadDefault)
  const addNode = useGraphStore((s) => s.addNode)
  const { screenToFlowPosition } = useReactFlow()
  const canvasRef = useRef<HTMLDivElement>(null)
  const { load: loadCatalog, status: catalogStatus } = catalog

  useEffect(() => {
    void loadCatalog()
  }, [loadCatalog])

  // The graph's node components need the catalog, so the default graph loads after it.
  useEffect(() => {
    if (catalogStatus === 'ready' && graphStatus === 'empty') void loadDefault()
  }, [catalogStatus, graphStatus, loadDefault])

  const addAtCenter = useCallback(
    (nodeType: string) => {
      const rect = canvasRef.current?.getBoundingClientRect()
      const center = rect ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 } : { x: 0, y: 0 }
      addNode(nodeType, screenToFlowPosition(center))
    },
    [addNode, screenToFlowPosition],
  )

  const error = catalog.error ?? graphError
  return (
    <div className="app">
      <header className="app__header">
        <h1>Pipeline Simulator</h1>
        <span className="app__status">
          {error ? `Could not reach the server: ${error}` : graphStatus === 'ready' ? '' : 'Loading…'}
        </span>
      </header>
      <main className="app__body">
        <Palette nodes={catalog.nodes} onAdd={addAtCenter} />
        <div className="app__canvas" ref={canvasRef}>
          {graphStatus === 'ready' && <Canvas />}
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <ReactFlowProvider>
      <Workbench />
    </ReactFlowProvider>
  )
}
