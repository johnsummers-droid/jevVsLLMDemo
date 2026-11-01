// View the reference graphs on the team canvas. With ?ref in the address the picker shows at any
// time; it stays for the workshop (user decision 2026-11-01). Picking a reference graph saves the
// team's graph first, then shows the reference read-only (never saved, Run disabled); "User
// defined" reloads the team's last saved graph. Those graphs are bundled from shared/fixtures/graphs.
// Without ?ref the picker appears after the official run, with graphs from the server (T40).
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

export const BUNDLED_REFERENCES = Object.entries(REFERENCE_GRAPHS).map(([name, { label }]) => ({ name, label }))

export function referenceViewerEnabled(search: string = window.location.search): boolean {
  return new URLSearchParams(search).has('ref')
}

/** The post-run reveal (T40): the server decides, so a refusal here only leaves a notice. */
export async function viewRevealed(name: string | null): Promise<void> {
  const g = useGraphStore.getState()
  if (name === null) return viewReference(null)
  if (g.teamId === null) return
  try {
    useGraphStore.getState().showReference(name, await api.getTeamReferenceGraph(g.teamId, name))
  } catch {
    useGraphStore.getState().setNotice('Could not load that reference graph. Try again.')
  }
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

