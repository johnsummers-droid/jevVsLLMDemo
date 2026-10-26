// An in-app link: a real href (open in a new tab works) that navigates without a page load.
import type { ReactNode } from 'react'
import { navigate } from '../lib/navigation'

export function Link({ to, children }: { to: string; children: ReactNode }) {
  return (
    <a
      href={to}
      onClick={(e) => {
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
        e.preventDefault()
        navigate(to)
      }}
    >
      {children}
    </a>
  )
}
