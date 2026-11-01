// The post-run reveal (T40): while graphs are locked, asks the server until it says the official run
// has ended. Polling keeps this simple and survives a reload or a reconnect; it stops at the answer.
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ReferenceGraphInfo } from '../types'

export const REVEAL_POLL_MS = 5000

export function useReveal(teamId: string, locked: boolean): ReferenceGraphInfo[] {
  const [graphs, setGraphs] = useState<ReferenceGraphInfo[]>([])
  useEffect(() => {
    setGraphs([])
    if (!locked) return
    let stopped = false
    let timer: number | undefined
    const check = async () => {
      try {
        const listing = await api.getTeamReferenceGraphs(teamId)
        if (stopped) return
        if (listing.available) {
          setGraphs(listing.graphs)
          return
        }
      } catch {
        // Offline or a restart: ask again.
      }
      if (!stopped) timer = window.setTimeout(() => void check(), REVEAL_POLL_MS)
    }
    void check()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [teamId, locked])
  return graphs
}
