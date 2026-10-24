// The team's graph, held in memory as React Flow nodes and edges (no persistence until M3). It
// starts from GET /api/graphs/default; the catalog must be loaded first.
import {
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type XYPosition,
} from '@xyflow/react'
import { create } from 'zustand'
import { api } from '../api/client'
import { checkConnection, type ConnectionCheck } from '../canvas/isValidConnection'
import { edgeId, flowNodeType, flowToGraph, graphToFlow } from '../lib/graphMapping'
import type { FlowEdge, FlowNode, Graph, NodeDefinition } from '../types'
import { useCatalogStore } from './catalogStore'

type GraphStatus = 'empty' | 'loading' | 'ready' | 'error'

interface GraphState {
  status: GraphStatus
  error: string | null
  nodes: FlowNode[]
  edges: FlowEdge[]
  setGraph: (graph: Graph) => void
  /** Replaces the graph with the server's default graph (ignored while a load is running). */
  loadDefault: () => Promise<void>
  /** Adds a node with the catalog's default params and returns its id. */
  addNode: (nodeType: string, position: XYPosition) => string
  moveNode: (id: string, position: XYPosition) => void
  /** Removes the node and every edge attached to it. */
  deleteNode: (id: string) => void
  /** Adds the edge if checkConnection allows it; returns the check either way. */
  connect: (connection: Connection) => ConnectionCheck
  deleteEdge: (id: string) => void
  onNodesChange: (changes: NodeChange<FlowNode>[]) => void
  onEdgesChange: (changes: EdgeChange<FlowEdge>[]) => void
  toGraph: () => Graph
}

const catalog = () => useCatalogStore.getState().byType

/** "<base>", then "<base>_2", "<base>_3", ... whichever is free. */
export function uniqueNodeId(base: string, nodes: FlowNode[]): string {
  const taken = new Set(nodes.map((n) => n.id))
  if (!taken.has(base)) return base
  let i = 2
  while (taken.has(`${base}_${i}`)) i++
  return `${base}_${i}`
}

export function defaultParams(definition: NodeDefinition): Record<string, unknown> {
  return Object.fromEntries(definition.params.map((spec) => [spec.key, structuredClone(spec.default)]))
}

export const useGraphStore = create<GraphState>()((set, get) => ({
  status: 'empty',
  error: null,
  nodes: [],
  edges: [],

  setGraph: (graph) => {
    const { nodes, edges } = graphToFlow(graph, catalog())
    set({ status: 'ready', error: null, nodes, edges })
  },

  loadDefault: async () => {
    if (get().status === 'loading') return
    set({ status: 'loading', error: null })
    try {
      get().setGraph(await api.getDefaultGraph())
    } catch (error) {
      set({ status: 'error', error: error instanceof Error ? error.message : String(error) })
    }
  },

  addNode: (nodeType, position) => {
    const definition = catalog()[nodeType]
    if (!definition) throw new Error(`unknown node type ${nodeType}`)
    const id = uniqueNodeId(nodeType, get().nodes)
    const node: FlowNode = {
      id,
      type: flowNodeType(nodeType, catalog()),
      position,
      data: { nodeType, params: defaultParams(definition), label: null },
    }
    set({ status: 'ready', nodes: [...get().nodes, node] })
    return id
  },

  moveNode: (id, position) => {
    set({ nodes: get().nodes.map((n) => (n.id === id ? { ...n, position } : n)) })
  },

  deleteNode: (id) => {
    set({
      nodes: get().nodes.filter((n) => n.id !== id),
      edges: get().edges.filter((e) => e.source !== id && e.target !== id),
    })
  },

  connect: (connection) => {
    const { nodes, edges } = get()
    const check = checkConnection(connection, { nodes, edges, catalog: catalog() })
    if (check.ok) {
      const { source, sourceHandle, target, targetHandle } = connection
      const edge: FlowEdge = {
        id: edgeId(source, sourceHandle ?? '', target, targetHandle ?? ''),
        source,
        sourceHandle,
        target,
        targetHandle,
      }
      set({ edges: [...edges, edge] })
    }
    return check
  },

  deleteEdge: (id) => {
    set({ edges: get().edges.filter((e) => e.id !== id) })
  },

  onNodesChange: (changes) => {
    const removed = new Set(changes.flatMap((c) => (c.type === 'remove' ? [c.id] : [])))
    set({
      nodes: applyNodeChanges(changes, get().nodes),
      edges: removed.size ? get().edges.filter((e) => !removed.has(e.source) && !removed.has(e.target)) : get().edges,
    })
  },

  onEdgesChange: (changes) => {
    set({ edges: applyEdgeChanges(changes, get().edges) })
  },

  toGraph: () => flowToGraph(get().nodes, get().edges),
}))
