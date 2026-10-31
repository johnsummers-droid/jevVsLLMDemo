// TEMPORARY quick fix (2026-10-31): view the reference graphs on the team canvas. The picker shows
// only when the page is opened with ?ref in the address. Picking a reference graph saves the team's
// graph first, then shows the reference read-only (never saved, Run disabled); "User defined"
// reloads the team's last saved graph. The graphs are bundled from shared/fixtures/graphs, so they
// are in the web bundle: hide or remove this before the workshop. The proper version is the
// facilitator view + post-run reveal task in plan1.txt (T40).
import defaultGraph from '../../../shared/fixtures/graphs/default.json'
import escalateAllGraph from '../../../shared/fixtures/graphs/escalate_all.json'
import strongGraph from '../../../shared/fixtures/graphs/strong.json'
import weakGraph from '../../../shared/fixtures/graphs/weak.json'
import { api } from '../api/client'
import { useGraphStore } from '../store/graphStore'
import { useSaveStore } from '../store/saveStore'
import type { Graph } from '../types'

export const REFERENCE_GRAPHS: Record<string, { label: string; graph: Graph }> = {
  default: { label: 'Starter (default)', graph: defaultGraph as Graph },
  weak: { label: 'Weak', graph: weakGraph as Graph },
  strong: { label: 'Strong', graph: strongGraph as Graph },
  escalate_all: { label: 'Escalate all', graph: escalateAllGraph as Graph },
}

export function referenceViewerEnabled(search: string = window.location.search): boolean {
  return new URLSearchParams(search).has('ref')
}

/** Shows a reference graph (saving the team's graph first), or the team's saved graph for null. */
export async function viewReference(name: string | null): Promise<void> {
  const g = useGraphStore.getState()
  if (name === null) {
    if (g.reference === null || g.teamId === null) return
    try {
      g.setStoredGraph(await api.getTeamGraph(g.teamId))
    } catch {
      g.setNotice('Could not load your graph. Try again.')
    }
    return
  }
  const reference = REFERENCE_GRAPHS[name]
  if (!reference) return
  if (g.reference === null && !g.locked) {
    await useSaveStore.getState().flush()
    const { status } = useSaveStore.getState()
    if (status === 'offline' || status === 'error') {
      useGraphStore.getState().setNotice('Your graph could not be saved, so it is still shown. Try again.')
      return
    }
  }
  useGraphStore.getState().showReference(name, reference.graph)
}

