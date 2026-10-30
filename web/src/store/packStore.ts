// Scenario pack summaries (GET /api/packs/{id}), loaded once each: the run UI colours its metrics
// against the pack's scoring targets.
import { create } from 'zustand'
import { api } from '../api/client'
import type { PackSummary } from '../types'

interface PackState {
  packs: Record<string, PackSummary>
  load: (packId: string) => Promise<void>
}

const loading = new Set<string>()

export const usePackStore = create<PackState>()((set, get) => ({
  packs: {},
  load: async (packId) => {
    if (get().packs[packId] || loading.has(packId)) return
    loading.add(packId)
    try {
      const pack = await api.getPack(packId)
      set({ packs: { ...get().packs, [packId]: pack } })
    } catch {
      // Without targets the metrics still show, uncoloured; the next run retries.
    } finally {
      loading.delete(packId)
    }
  },
}))
