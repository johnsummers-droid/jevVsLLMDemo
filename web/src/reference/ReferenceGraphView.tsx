// "Show reference graph" for the debrief (T40), on /facilitator and /screen: a picker and a
// read-only canvas of its own. It doesn't touch graphStore, which holds a team's graph.
import { Background, Controls, ReactFlow, ReactFlowProvider, useNodesInitialized, useReactFlow } from '@xyflow/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { PipelineEdge } from '../canvas/PipelineEdge'
import { graphToFlow } from '../lib/graphMapping'
import { nodeTypes } from '../nodes/nodeTypes'
import { useCatalogStore } from '../store/catalogStore'
import type { Graph, ReferenceGraphInfo } from '../types'

const edgeTypes = { default: PipelineEdge }
const HIDDEN = ''
const FIT = { padding: 0.08 }
// React Flow's default of 0.5 can't fit the strong graph in the facilitator page's narrow panel.
const MIN_ZOOM = 0.1

function ReadOnlyFlow({ graph }: { graph: Graph }) {
  const byType = useCatalogStore((s) => s.byType)
  const { nodes, edges } = useMemo(() => graphToFlow(graph, byType), [graph, byType])
  const { fitView } = useReactFlow()
  const measured = useNodesInitialized()
  const fitted = useRef(false)
  useEffect(() => {
    // The fitView prop can frame only the first node (see Canvas.tsx).
    if (measured && !fitted.current) {
      fitted.current = true
      void fitView(FIT)
    }
  }, [measured, fitView])
  return (
    <ReactFlow
      defaultNodes={nodes}
      defaultEdges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      deleteKeyCode={null}
      minZoom={MIN_ZOOM}
    >
      <Background />
      <Controls showInteractive={false} />
    </ReactFlow>
  )
}

export function ReferenceGraphView({ sessionCode }: { sessionCode: string }) {
  const loadCatalog = useCatalogStore((s) => s.load)
  const catalogReady = useCatalogStore((s) => s.status === 'ready')
  const [graphs, setGraphs] = useState<ReferenceGraphInfo[]>([])
  const [name, setName] = useState(HIDDEN)
  const [shown, setShown] = useState<{ name: string; graph: Graph } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void loadCatalog()
    api.getSessionReferenceGraphs(sessionCode).then(
      (listing) => setGraphs(listing.graphs),
      () => setError('Could not load the reference graphs.'),
    )
  }, [loadCatalog, sessionCode])

  useEffect(() => {
    setShown(null)
    setError(null)
    if (name === HIDDEN) return
    let current = true
    api.getSessionReferenceGraph(sessionCode, name).then(
      (graph) => {
        if (current) setShown({ name, graph })
      },
      () => {
        if (current) setError('Could not load that reference graph.')
      },
    )
    return () => {
      current = false
    }
  }, [name, sessionCode])

  return (
    <>
      <div className="page__row">
        <h2>Reference graphs</h2>
        <label className="reference-picker">
          Show reference graph
          <select value={name} onChange={(e) => setName(e.target.value)}>
            <option value={HIDDEN}>Hidden</option>
            {graphs.map((graph) => (
              <option key={graph.name} value={graph.name}>
                {graph.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && (
        <p className="page__error" role="alert">
          {error}
        </p>
      )}
      {shown && catalogReady && (
        <div className="reference-view" role="group" aria-label={`Reference graph ${shown.name}`}>
          <ReactFlowProvider key={shown.name}>
            <ReadOnlyFlow graph={shown.graph} />
          </ReactFlowProvider>
        </div>
      )}
    </>
  )
}
