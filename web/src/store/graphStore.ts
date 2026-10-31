// The team's graph, held in memory as React Flow nodes and edges. It is loaded from the team's
// stored graph (GET /api/teams/{id}/graph) or the server's default graph; the catalog must be
// loaded first. saveStore saves it back; `baseline` is the signature of the last saved graph.
// While `locked`, every edit below is refused (the facilitator's "pencils down").
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
import { edgeId, expandOutputs, flowNodeType, flowToGraph, graphToFlow } from '../lib/graphMapping'
import type { FlowEdge, FlowNode, Graph, NodeDefinition, StoredGraph } from '../types'
import { useCatalogStore } from './catalogStore'

type GraphStatus = 'empty' | 'loading' | 'ready' | 'error'

interface GraphState {
  status: GraphStatus
  error: string | null
  nodes: FlowNode[]
  edges: FlowEdge[]
  /** A short message for the canvas (refused connection, pruned edges); null when none. */
  notice: string | null
  /** The team whose stored graph is loaded, its version and lock; null/0/false for the default graph. */
  teamId: string | null
  version: number
  locked: boolean
  /**
   * TEMPORARY (?ref viewer): the reference graph shown instead of the team's graph, or null.
   * While set, the graph is read-only and never saved; setStoredGraph clears it.
   */
  reference: string | null
  /** Shows a reference graph read-only in place of the team's graph (the caller saves first). */
  showReference: (name: string, graph: Graph) => void
  /** graphSignature of the graph as last loaded or saved; the graph has unsaved changes when it differs. */
  baseline: string | null
  setNotice: (notice: string | null) => void
  setGraph: (graph: Graph) => void
  /** Loads a stored graph (initial load, a 409 reload, a reset) as the new baseline. */
  setStoredGraph: (stored: StoredGraph) => void
  /** Records a successful save of the graph with that signature. */
  markSaved: (version: number, signature: string) => void
  setLocked: (locked: boolean) => void
  /** Replaces the graph with the server's default graph (ignored while a load is running). */
  loadDefault: () => Promise<void>
  /** Replaces the graph with the team's stored graph (ignored while a load is running). */
  loadTeamGraph: (teamId: string) => Promise<void>
  /** Back to the empty state, e.g. when the team signs out. */
  clear: () => void
  /** Adds a node with the catalog's default params (nudged off any node at that spot); returns its id, or '' when locked. */
  addNode: (nodeType: string, position: XYPosition) => string
  moveNode: (id: string, position: XYPosition) => void
  /** Removes the node and every edge attached to it. */
  deleteNode: (id: string) => void
  /** Adds the edge if checkConnection allows it; returns the check either way. */
  connect: (connection: Connection) => ConnectionCheck
  deleteEdge: (id: string) => void
  /**
   * Sets one param (the caller checks the value). Edges from branch ports that the new value
   * removes are dropped, with a notice; their ids are returned.
   */
  updateParam: (nodeId: string, key: string, value: unknown) => string[]
  onNodesChange: (changes: NodeChange<FlowNode>[]) => void
  onEdgesChange: (changes: EdgeChange<FlowEdge>[]) => void
  toGraph: () => Graph
}

const catalog = () => useCatalogStore.getState().byType

/** Everything that is saved, positions included (unlike validationSignature). */
export function graphSignature(graph: Graph): string {
  return JSON.stringify(graph)
}

const LOCKED: ConnectionCheck = { ok: false, reason: 'locked', message: 'The graph is locked.' }

/** "<base>", then "<base>_2", "<base>_3", ... whichever is free. */
export function uniqueNodeId(base: string, nodes: FlowNode[]): string {
  const taken = new Set(nodes.map((n) => n.id))
  if (!taken.has(base)) return base
  let i = 2
  while (taken.has(`${base}_${i}`)) i++
  return `${base}_${i}`
}

const NUDGE = 32

/** The position, moved diagonally until no node starts within NUDGE/2 of it (repeated adds stay visible). */
export function freePosition(position: XYPosition, nodes: FlowNode[]): XYPosition {
  let { x, y } = position
  while (nodes.some((n) => Math.abs(n.position.x - x) < NUDGE / 2 && Math.abs(n.position.y - y) < NUDGE / 2)) {
    x += NUDGE
    y += NUDGE
  }
  return { x, y }
}

export function defaultParams(definition: NodeDefinition): Record<string, unknown> {
  return Object.fromEntries(definition.params.map((spec) => [spec.key, structuredClone(spec.default)]))
}

export const useGraphStore = create<GraphState>()((set, get) => {
  const load = async <T>(request: () => Promise<T>, apply: (value: T) => void) => {
    if (get().status === 'loading') return
    set({ status: 'loading', error: null })
    try {
      apply(await request())
    } catch (error) {
      set({ status: 'error', error: error instanceof Error ? error.message : String(error) })
    }
  }

  const editable = () => !get().locked && get().reference === null

  return {
    status: 'empty',
    error: null,
    nodes: [],
    edges: [],
    notice: null,
    teamId: null,
    version: 0,
    locked: false,
    reference: null,
    baseline: null,

    setNotice: (notice) => set({ notice }),

    setGraph: (graph) => {
      const { nodes, edges } = graphToFlow(graph, catalog())
      set({ status: 'ready', error: null, nodes, edges, baseline: graphSignature(flowToGraph(nodes, edges)) })
    },

    setStoredGraph: (stored) => {
      get().setGraph(stored.graph)
      set({ teamId: stored.teamId, version: stored.version, locked: stored.locked, reference: null })
    },

    showReference: (name, graph) => {
      // reference first, so autosave never sees the reference graph as an unsaved edit.
      set({ reference: name })
      get().setGraph(graph)
    },

    markSaved: (version, signature) => set({ version, baseline: signature }),

    setLocked: (locked) => set({ locked }),

    loadDefault: () => load(api.getDefaultGraph, get().setGraph),

    loadTeamGraph: (teamId) => load(() => api.getTeamGraph(teamId), get().setStoredGraph),

    clear: () =>
      set({
        status: 'empty',
        error: null,
        nodes: [],
        edges: [],
        notice: null,
        teamId: null,
        version: 0,
        locked: false,
        reference: null,
        baseline: null,
      }),

    addNode: (nodeType, position) => {
      if (!editable()) return ''
      const definition = catalog()[nodeType]
      if (!definition) throw new Error(`unknown node type ${nodeType}`)
      const id = uniqueNodeId(nodeType, get().nodes)
      const node: FlowNode = {
        id,
        type: flowNodeType(nodeType, catalog()),
        position: freePosition(position, get().nodes),
        data: { nodeType, params: defaultParams(definition), label: null },
      }
      set({ status: 'ready', nodes: [...get().nodes, node] })
      return id
    },

    moveNode: (id, position) => {
      if (!editable()) return
      set({ nodes: get().nodes.map((n) => (n.id === id ? { ...n, position } : n)) })
    },

    deleteNode: (id) => {
      if (!editable()) return
      set({
        nodes: get().nodes.filter((n) => n.id !== id),
        edges: get().edges.filter((e) => e.source !== id && e.target !== id),
      })
    },

    connect: (connection) => {
      if (!editable()) return LOCKED
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
      if (!editable()) return
      set({ edges: get().edges.filter((e) => e.id !== id) })
    },

    updateParam: (nodeId, key, value) => {
      if (!editable()) return []
      const node = get().nodes.find((n) => n.id === nodeId)
      if (!node) return []
      const definition = catalog()[node.data.nodeType]
      const params = { ...node.data.params, [key]: value }
      const outputIds = (p: Record<string, unknown> | undefined) =>
        new Set(definition ? expandOutputs(definition, p).map((port) => port.id) : [])
      const before = outputIds(node.data.params)
      const after = outputIds(params)
      // Only edges that were on a real port lose it; edges the server already flags stay.
      const dropped = get().edges.filter(
        (e) => e.source === nodeId && before.has(e.sourceHandle ?? '') && !after.has(e.sourceHandle ?? ''),
      )
      const droppedIds = new Set(dropped.map((e) => e.id))
      set({
        nodes: get().nodes.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, params } } : n)),
        edges: get().edges.filter((e) => !droppedIds.has(e.id)),
        ...(dropped.length > 0 && {
          notice:
            `Removed ${dropped.length} connection${dropped.length > 1 ? 's' : ''} from branches that no longer ` +
            `exist: ${dropped.map((e) => `${e.sourceHandle} → ${e.target}`).join(', ')}.`,
        }),
      })
      return dropped.map((e) => e.id)
    },

    onNodesChange: (changes) => {
      // Locked: selection and measuring still apply; moves and removals do not.
      if (!editable()) changes = changes.filter((c) => c.type === 'select' || c.type === 'dimensions')
      const removed = new Set(changes.flatMap((c) => (c.type === 'remove' ? [c.id] : [])))
      set({
        nodes: applyNodeChanges(changes, get().nodes),
        edges: removed.size ? get().edges.filter((e) => !removed.has(e.source) && !removed.has(e.target)) : get().edges,
      })
    },

    onEdgesChange: (changes) => {
      if (!editable()) changes = changes.filter((c) => c.type === 'select')
      set({ edges: applyEdgeChanges(changes, get().edges) })
    },

    toGraph: () => flowToGraph(get().nodes, get().edges),
  }
})
