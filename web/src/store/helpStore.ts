// The help panel (plan1.txt S2): one panel for the whole app, showing one node type's help.
// "One at a time" holds by construction: there is a single nodeType.
import { create } from 'zustand'

export const HELP_PANEL_ID = 'help-panel'
/** Panel height as a fraction of the canvas area (S3); CSS also keeps it at least 160 px. */
export const DEFAULT_HELP_HEIGHT = 0.4
export const MAX_HELP_HEIGHT = 0.8
export const MIN_HELP_HEIGHT = 0.1
const HEIGHT_KEY = 'pipeline-sim:help-height'

export const clampHelpHeight = (fraction: number) =>
  Math.min(MAX_HELP_HEIGHT, Math.max(MIN_HELP_HEIGHT, fraction))

// Remembered per browser; storage can be missing or blocked, so every access is guarded.
function loadHeight(): number {
  try {
    const stored = Number(window.localStorage.getItem(HEIGHT_KEY))
    return stored ? clampHelpHeight(stored) : DEFAULT_HELP_HEIGHT
  } catch {
    return DEFAULT_HELP_HEIGHT
  }
}

function saveHeight(fraction: number) {
  try {
    window.localStorage.setItem(HEIGHT_KEY, String(fraction))
  } catch {
    // not remembered; the panel still works
  }
}

interface HelpState {
  nodeType: string | null
  /** The "?" that opened the panel; focus goes back to it on close (S8). */
  opener: HTMLElement | null
  height: number
  open: (nodeType: string, opener?: HTMLElement | null) => void
  /** The "?" of the type already shown closes the panel; any other swaps the content. */
  toggle: (nodeType: string, opener?: HTMLElement | null) => void
  close: () => void
  setHeight: (fraction: number) => void
}

export const useHelpStore = create<HelpState>()((set, get) => ({
  nodeType: null,
  opener: null,
  height: loadHeight(),

  open: (nodeType, opener = null) => set({ nodeType, opener }),

  toggle: (nodeType, opener = null) => {
    if (get().nodeType === nodeType) get().close()
    else get().open(nodeType, opener)
  },

  close: () => {
    const { nodeType, opener } = get()
    if (nodeType === null) return
    set({ nodeType: null, opener: null })
    if (opener?.isConnected) opener.focus()
  },

  setHeight: (fraction) => {
    const height = clampHelpHeight(fraction)
    set({ height })
    saveHeight(height)
  },
}))
