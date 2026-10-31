// The editable pipeline canvas (read-only while the graph is locked or a run plays). Must be rendered inside a
// ReactFlowProvider, and mounted once the graph has loaded so the first fitView frames it.
import {
  Background,
  Controls,
  ReactFlow,
  useReactFlow,
  useStore,
  type Connection,
  type Edge,
  type FinalConnectionState,
} from '@xyflow/react'
import { useCallback, useEffect, useRef, type DragEvent } from 'react'
import { nodeTypes } from '../nodes/nodeTypes'
import { NODE_DRAG_TYPE } from '../palette/NodeCard'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { useReadOnly } from '../store/runStore'
import { checkConnection, type Link } from './isValidConnection'
import { PipelineEdge } from './PipelineEdge'
import { startPulses } from './pulses'

// Replaces React Flow's default edge, so every edge can carry a validation badge.
const edgeTypes = { default: PipelineEdge }

const NOTICE_MS = 4000
// Below this zoom a node's "?" is too small to hit, so it's hidden (S8); palette and Inspector keep theirs.
export const HELP_MIN_ZOOM = 0.6

export function Canvas() {
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const onNodesChange = useGraphStore((s) => s.onNodesChange)
  const onEdgesChange = useGraphStore((s) => s.onEdgesChange)
  const connect = useGraphStore((s) => s.connect)
  const addNode = useGraphStore((s) => s.addNode)
  const catalog = useCatalogStore((s) => s.byType)
  const { fitView, screenToFlowPosition } = useReactFlow()
  const notice = useGraphStore((s) => s.notice)
  const setNotice = useGraphStore((s) => s.setNotice)
  const locked = useReadOnly() // the graph is locked, or the team's run is playing (Q6)
  const zoomedOut = useStore((s) => s.transform[2] < HELP_MIN_ZOOM)

  useEffect(() => startPulses(), [])

  // The fitView prop can run before every node is measured and frame only the first one, so fit
  // once (per mount) when all nodes have their size. React Flow's store outlives this component
  // (the provider is on the page), so after a remount with another graph (the ?ref viewer) it can
  // still report the previous graph as measured: wait until the measured nodes are this graph's.
  const graphIds = useGraphStore((s) => s.nodes.map((n) => n.id).join('|'))
  const measured = useStore(
    (s) => s.nodes.map((n) => n.id).join('|') === graphIds && s.nodes.every((n) => n.measured?.width),
  )
  const fitted = useRef(false)
  useEffect(() => {
    if (measured && !fitted.current) {
      fitted.current = true
      void fitView()
    }
  }, [measured, fitView])

  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(null), NOTICE_MS)
    return () => clearTimeout(timer)
  }, [notice, setNotice])

  const isValidConnection = useCallback(
    (link: Edge | Connection) => checkConnection(link, { nodes, edges, catalog }).ok,
    [nodes, edges, catalog],
  )

  const onConnect = useCallback(
    (connection: Connection) => {
      const check = connect(connection)
      if (!check.ok) setNotice(check.message)
    },
    [connect, setNotice],
  )

  // React Flow only reports that a drop was refused; say why.
  const onConnectEnd = useCallback(
    (_event: MouseEvent | TouchEvent, state: FinalConnectionState) => {
      const { fromHandle, toHandle, isValid } = state
      if (isValid || !fromHandle || !toHandle) return
      const [from, to] = fromHandle.type === 'source' ? [fromHandle, toHandle] : [toHandle, fromHandle]
      const link: Link = { source: from.nodeId, sourceHandle: from.id, target: to.nodeId, targetHandle: to.id }
      const check = checkConnection(link, { nodes, edges, catalog })
      if (!check.ok) setNotice(check.message)
    },
    [nodes, edges, catalog, setNotice],
  )

  const onDragOver = useCallback((event: DragEvent) => {
    if (!event.dataTransfer.types.includes(NODE_DRAG_TYPE)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: DragEvent) => {
      const nodeType = event.dataTransfer.getData(NODE_DRAG_TYPE)
      if (!nodeType || locked) return
      event.preventDefault()
      addNode(nodeType, screenToFlowPosition({ x: event.clientX, y: event.clientY }))
    },
    [addNode, screenToFlowPosition, locked],
  )

  return (
    <div className={`canvas${zoomedOut ? ' canvas--zoomed-out' : ''}`} onDragOver={onDragOver} onDrop={onDrop}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onConnectEnd={onConnectEnd}
        isValidConnection={isValidConnection}
        nodesDraggable={!locked}
        nodesConnectable={!locked}
        edgesReconnectable={!locked}
        deleteKeyCode={locked ? null : undefined}
        minZoom={0.2}
        colorMode="system"
      >
        <Background />
        <Controls />
      </ReactFlow>
      {notice && (
        <div className="canvas__notice" role="status">
          {notice}
        </div>
      )}
    </div>
  )
}
