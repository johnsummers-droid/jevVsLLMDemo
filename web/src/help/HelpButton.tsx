// The "?" that opens a node type's help (plan1.txt S1, S8). Always enabled, also while read-only.
// On a canvas node it must neither select nor drag the node: React Flow's nodrag/nopan classes
// stop the drag, and stopping propagation keeps clicks and keys away from the node.
import type { SyntheticEvent } from 'react'
import { HELP_PANEL_ID, useHelpStore } from '../store/helpStore'
import type { NodeDefinition } from '../types'

const stop = (event: SyntheticEvent) => event.stopPropagation()

export function HelpButton({ definition, className }: { definition: NodeDefinition; className?: string }) {
  const shown = useHelpStore((s) => s.nodeType === definition.type)
  const toggle = useHelpStore((s) => s.toggle)
  return (
    <button
      type="button"
      className={['help-button', 'nodrag', 'nopan', className].filter(Boolean).join(' ')}
      aria-label={`Help: ${definition.title}`}
      aria-expanded={shown}
      aria-controls={shown ? HELP_PANEL_ID : undefined}
      title={`Help: ${definition.title}`}
      onClick={(event) => {
        event.stopPropagation()
        toggle(definition.type, event.currentTarget)
      }}
      onPointerDown={stop}
      onMouseDown={stop}
      onDoubleClick={stop}
      onKeyDown={stop}
      draggable={false}
      onDragStart={(event) => {
        event.preventDefault()
        event.stopPropagation()
      }}
    >
      ?
    </button>
  )
}
