// Autosave of the team's graph (plan1.txt T15). SAVE_DEBOUNCE_MS after the last change, positions
// included, the graph is PUT with the version it was loaded at. One request is in flight at a time;
// changes made meanwhile are saved after it. 409: the server's graph (the response body) replaces
// the local one, with a notice. 423: the graph becomes read-only. Network and server errors retry
// with backoff. A save still pending at pagehide is sent with fetch keepalive.
// While the live socket is down (runStore.connection is not 'live'), the graph is also polled
// every SYNC_POLL_MS: that is how an idle team still sees the facilitator lock or unlock, and how
// a tab picks up another tab's save. While it is live, locks arrive over the socket (Q5).
import { create } from 'zustand'
import { ApiError, api } from '../api/client'
import type { StoredGraph } from '../types'
import { graphSignature, useGraphStore } from './graphStore'
import { useRunStore } from './runStore'

export const SAVE_DEBOUNCE_MS = 1000
export const RETRY_BASE_MS = 1000
export const RETRY_MAX_MS = 30_000
export const SYNC_POLL_MS = 10_000
export const RELOADED_NOTICE = 'Your graph was changed elsewhere; reloaded.'

export type SaveStatus = 'saved' | 'pending' | 'saving' | 'offline' | 'locked' | 'error'

interface SaveState {
  status: SaveStatus
  error: string | null
  /** Saves pending changes now (e.g. before signing out); resolves when the save is done. */
  flush: () => Promise<void>
  /** Replaces the team's graph with the default graph on the server, then shows it. */
  reset: () => Promise<void>
}

const graph = () => useGraphStore.getState()
const setStatus = (status: SaveStatus, error: string | null = null) => useSaveStore.setState({ status, error })

let debounceTimer: ReturnType<typeof setTimeout> | undefined
let retryTimer: ReturnType<typeof setTimeout> | undefined
let pollTimer: ReturnType<typeof setInterval> | undefined
let retryDelay = 0
let inFlight: Promise<void> | null = null

function isDirty(): boolean {
  const g = graph()
  return g.status === 'ready' && g.teamId !== null && graphSignature(g.toGraph()) !== g.baseline
}

/** The status when nothing is scheduled: saved, or pending when edits are waiting. */
function settle(): void {
  if (graph().locked) setStatus('locked')
  else if (isDirty()) setStatus('pending')
  else setStatus('saved')
}

function loadServerGraph(stored: StoredGraph): void {
  graph().setStoredGraph(stored)
  graph().setNotice(RELOADED_NOTICE)
}

function onSaveError(error: unknown): void {
  if (error instanceof ApiError && error.status === 409) {
    loadServerGraph(error.body as StoredGraph)
    settle()
  } else if (error instanceof ApiError && error.status === 423) {
    graph().setLocked(true)
  } else if (error instanceof ApiError && error.status === 401) {
    setStatus('error', 'Signed out.') // the client has already gone back to /join
  } else if (error instanceof ApiError && error.status < 500) {
    setStatus('error', error.message)
  } else {
    // Network error or a server error: keep the edits and retry with backoff.
    retryDelay = Math.min(Math.max(retryDelay * 2, RETRY_BASE_MS), RETRY_MAX_MS)
    setStatus('offline')
    retryTimer = setTimeout(() => {
      retryTimer = undefined
      void save()
    }, retryDelay)
  }
}

/** Saves now if the graph has unsaved changes. A call during a request is picked up after it. */
async function save(): Promise<void> {
  clearTimeout(debounceTimer)
  debounceTimer = undefined
  if (inFlight || retryTimer) return
  const g = graph()
  if (g.locked || !isDirty() || g.teamId === null) return settle()

  const teamId = g.teamId
  const sent = g.toGraph()
  const signature = graphSignature(sent)
  setStatus('saving')
  inFlight = (async () => {
    try {
      const stored = await api.saveTeamGraph(teamId, g.version, sent)
      if (graph().teamId !== teamId) return // signed out meanwhile
      graph().markSaved(stored.version, signature)
      retryDelay = 0
      settle()
    } catch (error) {
      if (graph().teamId === teamId) onSaveError(error)
    }
  })()
  await inFlight
  inFlight = null
  // Edits made during the request: save them now unless a debounce or retry is already waiting.
  if (isDirty() && !debounceTimer && !retryTimer && !graph().locked) await save()
}

/** Brings the lock state, and an idle graph, up to date with the server. */
async function sync(teamId: string): Promise<void> {
  let stored: StoredGraph
  try {
    stored = await api.getTeamGraph(teamId)
  } catch {
    return // offline or a server error: try again on the next tick (a 401 has signed the team out)
  }
  const g = graph()
  if (g.teamId !== teamId) return
  if (stored.locked) {
    if (!g.locked) g.setLocked(true)
    return
  }
  const idle = !inFlight && !debounceTimer && !retryTimer && !isDirty()
  if (stored.version !== g.version && (g.locked || idle)) loadServerGraph(stored)
  else if (g.locked) g.setLocked(false)
  if (isDirty() && !debounceTimer) await save() // edits kept from before the lock
}

function startSyncPoll(teamId: string): void {
  clearInterval(pollTimer)
  pollTimer = setInterval(() => void sync(teamId), SYNC_POLL_MS)
}

function onGraphChange(): void {
  const g = graph()
  if (g.status !== 'ready' || g.teamId === null) return
  if (g.locked) {
    clearTimeout(debounceTimer)
    debounceTimer = undefined
    setStatus('locked')
    return
  }
  if (retryTimer || inFlight) return // the retry, or the end of the request, saves the latest graph
  if (!isDirty()) return settle()
  setStatus('pending')
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => void save(), SAVE_DEBOUNCE_MS)
}

function onPageHide(): void {
  const g = graph()
  if (!isDirty() || inFlight || g.locked || g.teamId === null) return
  void api.saveTeamGraph(g.teamId, g.version, g.toGraph(), { keepalive: true }).catch(() => {})
}

export const useSaveStore = create<SaveState>()(() => ({
  status: 'saved',
  error: null,
  flush: async () => {
    if (inFlight) await inFlight
    await save()
  },
  reset: async () => {
    clearTimeout(debounceTimer)
    debounceTimer = undefined
    if (inFlight) await inFlight
    const teamId = graph().teamId
    if (teamId === null) return
    try {
      graph().setStoredGraph(await api.resetTeamGraph(teamId))
      settle()
    } catch (error) {
      if (error instanceof ApiError && error.status === 423) graph().setLocked(true)
      else graph().setNotice('Resetting the graph failed. Try again.')
    }
  },
}))

/** Starts autosaving the loaded team graph; returns a function that stops it. */
export function startAutosave(): () => void {
  const unsubscribe = useGraphStore.subscribe((state, previous) => {
    if (
      state.nodes !== previous.nodes ||
      state.edges !== previous.edges ||
      state.status !== previous.status ||
      state.baseline !== previous.baseline ||
      state.locked !== previous.locked
    ) {
      onGraphChange()
    }
  })
  window.addEventListener('pagehide', onPageHide)
  // One sync poll for whichever team's graph is loaded, only while the live socket is down.
  let polledTeam: string | null = null
  const followTeam = () => {
    const teamId = useRunStore.getState().connection === 'live' ? null : graph().teamId
    if (teamId === polledTeam) return
    polledTeam = teamId
    clearInterval(pollTimer)
    pollTimer = undefined
    if (teamId !== null) startSyncPoll(teamId)
  }
  const unsubscribeTeam = useGraphStore.subscribe(followTeam)
  const unsubscribeLive = useRunStore.subscribe(followTeam)
  followTeam()
  onGraphChange()
  return () => {
    unsubscribe()
    unsubscribeTeam()
    unsubscribeLive()
    window.removeEventListener('pagehide', onPageHide)
    clearTimeout(debounceTimer)
    clearTimeout(retryTimer)
    clearInterval(pollTimer)
    debounceTimer = retryTimer = pollTimer = undefined
    retryDelay = 0
    setStatus('saved')
  }
}
