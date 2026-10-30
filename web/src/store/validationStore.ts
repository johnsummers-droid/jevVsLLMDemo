// Server-side validation of the current graph (POST /api/graphs/validate), debounced after each
// change. Moving a node does not trigger it: positions do not affect validity.
import { create } from 'zustand'
import { api } from '../api/client'
import { EMPTY_INDEX, indexIssues, type IssueIndex } from '../lib/issues'
import type { Graph, ValidationReport } from '../types'
import { useGraphStore } from './graphStore'

export const VALIDATE_DEBOUNCE_MS = 500

type ValidationStatus = 'idle' | 'pending' | 'done' | 'error'

interface ValidationState {
  status: ValidationStatus
  report: ValidationReport | null
  index: IssueIndex
  error: string | null
  /** Validates now; a response that arrives after a newer request started is ignored. */
  validate: (graph: Graph) => Promise<void>
}

let latestRequest = 0

export const useValidationStore = create<ValidationState>()((set) => ({
  status: 'idle',
  report: null,
  index: EMPTY_INDEX,
  error: null,
  validate: async (graph) => {
    const request = ++latestRequest
    set({ status: 'pending', error: null })
    try {
      const report = await api.validateGraph(graph)
      if (request !== latestRequest) return
      set({ status: 'done', report, index: indexIssues(report) })
    } catch (error) {
      if (request !== latestRequest) return
      set({ status: 'error', error: error instanceof Error ? error.message : String(error) })
    }
  },
}))

/** The graph minus node positions and React Flow UI state: what validation depends on. */
export function validationSignature(graph: Graph): string {
  return JSON.stringify({
    nodes: graph.nodes.map((node) => ({ ...node, position: undefined })),
    edges: graph.edges,
  })
}

/**
 * Validates the loaded graph, then again VALIDATE_DEBOUNCE_MS after the last change that matters.
 * Returns a function that stops it.
 */
export function startAutoValidation(delayMs = VALIDATE_DEBOUNCE_MS): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined
  let lastSignature: string | null = null

  const onGraphChange = () => {
    const graphState = useGraphStore.getState()
    if (graphState.status !== 'ready') return
    const signature = validationSignature(graphState.toGraph())
    if (signature === lastSignature) return
    lastSignature = signature
    clearTimeout(timer)
    useValidationStore.setState({ status: 'pending' })
    timer = setTimeout(() => void useValidationStore.getState().validate(useGraphStore.getState().toGraph()), delayMs)
  }

  const unsubscribe = useGraphStore.subscribe((state, previous) => {
    if (state.nodes !== previous.nodes || state.edges !== previous.edges || state.status !== previous.status) {
      onGraphChange()
    }
  })
  onGraphChange()
  return () => {
    unsubscribe()
    clearTimeout(timer)
  }
}
