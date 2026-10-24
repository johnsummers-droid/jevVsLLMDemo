// The node catalog, loaded once from GET /api/catalog. The browser only gets metadata; the server
// runs every node.
import { create } from 'zustand'
import { api } from '../api/client'
import type { NodeDefinition } from '../types'

type CatalogStatus = 'idle' | 'loading' | 'ready' | 'error'

interface CatalogState {
  status: CatalogStatus
  nodes: NodeDefinition[]
  byType: Record<string, NodeDefinition>
  error: string | null
  /** Fetches the catalog unless it is loaded or loading; after an error it tries again. */
  load: () => Promise<void>
}

export const useCatalogStore = create<CatalogState>()((set, get) => ({
  status: 'idle',
  nodes: [],
  byType: {},
  error: null,
  load: async () => {
    const { status } = get()
    if (status === 'loading' || status === 'ready') return
    set({ status: 'loading', error: null })
    try {
      const { nodes } = await api.getCatalog()
      set({
        status: 'ready',
        nodes,
        byType: Object.fromEntries(nodes.map((node) => [node.type, node])),
      })
    } catch (error) {
      set({ status: 'error', error: error instanceof Error ? error.message : String(error) })
    }
  },
}))
