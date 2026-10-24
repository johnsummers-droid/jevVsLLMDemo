// Wire types come from generated.ts (do not edit that file). UI-only types are added here as the
// canvas needs them (plan1.txt section 2b).
import type { Edge, Node } from '@xyflow/react'
import type { GraphNode } from './generated'

export type * from './generated'

/** React Flow node data; holds what GraphNode needs beyond id and position, unchanged. */
export type FlowNodeData = {
  nodeType: GraphNode['type']
  params: GraphNode['params']
  label: GraphNode['label']
}

/** React Flow node; its `type` is the catalog category (one component per category). */
export type FlowNode = Node<FlowNodeData>

/** React Flow edge; sourceHandle/targetHandle are the GraphEdge port ids. */
export type FlowEdge = Edge
