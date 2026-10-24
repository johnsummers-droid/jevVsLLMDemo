// The editable pipeline canvas. Must be rendered inside a ReactFlowProvider, and mounted once the
// graph has loaded so the first fitView frames it.
import {
  Background,
  Controls,
  ReactFlow,
  useNodesInitialized,
  useReactFlow,
  type Connection,
  type Edge,
  type FinalConnectionState,
} from '@xyflow/react'
import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import { nodeTypes } from '../nodes/nodeTypes'
import { NODE_DRAG_TYPE } from '../palette/NodeCard'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { checkConnection, type Link } from './isValidConnection'

const NOTICE_MS = 4000

export function Canvas() {
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const onNodesChange = useGraphStore((s) => s.onNodesChange)
  const onEdgesChange = useGraphStore((s) => s.onEdgesChange)
  const connect = useGraphStore((s) => s.connect)
  const addNode = useGraphStore((s) => s.addNode)
  const catalog = useCatalogStore((s) => s.byType)
  const { fitView, screenToFlowPosition } = useReactFlow()
  const [notice, setNotice] = useState<string | null>(null)

  // The fitView prop can run before every node is measured and frame only the first one, so fit
  // once all nodes have their size.
  const nodesInitialized = useNodesInitialized()
  const fitted = useRef(false)
  useEffect(() => {
    if (nodesInitialized && !fitted.current) {
      fitted.current = true
      void fitView()
    }
  }, [nodesInitialized, fitView])

  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(null), NOTICE_MS)
    return () => clearTimeout(timer)
  }, [notice])

  const isValidConnection = useCallback(
    (link: Edge | Connection) => checkConnection(link, { nodes, edges, catalog }).ok,
    [nodes, edges, catalog],
  )

  const onConnect = useCallback(
    (connection: Connection) => {
      const check = connect(connection)
      if (!check.ok) setNotice(check.message)
    },
    [connect],
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
    [nodes, edges, catalog],
  )

  const onDragOver = useCallback((event: DragEvent) => {
    if (!event.dataTransfer.types.includes(NODE_DRAG_TYPE)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: DragEvent) => {
      const nodeType = event.dataTransfer.getData(NODE_DRAG_TYPE)
      if (!nodeType) return
      event.preventDefault()
      addNode(nodeType, screenToFlowPosition({ x: event.clientX, y: event.clientY }))
    },
    [addNode, screenToFlowPosition],
  )

  return (
    <div className="canvas" onDragOver={onDragOver} onDrop={onDrop}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onConnectEnd={onConnectEnd}
        isValidConnection={isValidConnection}
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
