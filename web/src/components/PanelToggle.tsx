// The caret in a circle on a side panel's inner edge. It points the way the panel will move: towards
// the outer edge while the panel is open, towards the canvas's centre while it is collapsed.
interface PanelToggleProps {
  side: 'left' | 'right'
  /** What the panel is called, for screen readers ("Collapse <name>"). */
  name: string
  collapsed: boolean
  onToggle: () => void
}

export function PanelToggle({ side, name, collapsed, onToggle }: PanelToggleProps) {
  const pointsLeft = (side === 'left') !== collapsed
  return (
    <button
      type="button"
      className={`panel-toggle panel-toggle--${side}${collapsed ? ' panel-toggle--collapsed' : ''}`}
      aria-label={`${collapsed ? 'Expand' : 'Collapse'} ${name}`}
      aria-expanded={!collapsed}
      title={`${collapsed ? 'Show' : 'Hide'} ${name}`}
      data-points={pointsLeft ? 'left' : 'right'}
      onClick={onToggle}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={pointsLeft ? 'm15 5-7 7 7 7' : 'm9 5 7 7-7 7'} />
      </svg>
    </button>
  )
}
