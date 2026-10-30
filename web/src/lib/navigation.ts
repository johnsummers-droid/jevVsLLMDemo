// Pages are picked from location.pathname (decision P6): no router dependency. navigate() pushes a
// history entry and fires popstate so usePathname() subscribers re-render.
import { useSyncExternalStore } from 'react'

export const PATHS = {
  join: '/join',
  team: '/team',
  facilitator: '/facilitator',
  screen: '/screen',
} as const

export type Page = keyof typeof PATHS

/** The page for a pathname (a trailing slash is ignored); null when it names no page. */
export function pageFromPath(pathname: string): Page | null {
  const path = pathname.replace(/\/+$/, '') || '/'
  const entry = Object.entries(PATHS).find(([, p]) => p === path)
  return entry ? (entry[0] as Page) : null
}

export function navigate(path: string, { replace = false }: { replace?: boolean } = {}): void {
  if (window.location.pathname === path) return
  if (replace) window.history.replaceState(null, '', path)
  else window.history.pushState(null, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener('popstate', onChange)
  return () => window.removeEventListener('popstate', onChange)
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname)
}
