import type { DragEvent } from 'react'
import { HelpButton } from '../help/HelpButton'
import { CategoryIcon } from '../nodes/CategoryIcon'
import type { NodeDefinition } from '../types'

/** dataTransfer type for a palette drag; the canvas reads the node type from it on drop. */
export const NODE_DRAG_TYPE = 'application/x-pipeline-node'

interface NodeCardProps {
  definition: NodeDefinition
  onAdd: (nodeType: string) => void
  disabled?: boolean
}

// Buttons can't nest, so the card holds the add button and the help button side by side (S8).
// Help stays enabled when the card is disabled.
export function NodeCard({ definition, onAdd, disabled = false }: NodeCardProps) {
  const onDragStart = (event: DragEvent) => {
    event.dataTransfer.setData(NODE_DRAG_TYPE, definition.type)
    event.dataTransfer.effectAllowed = 'move'
  }
  return (
    <div className={`node-card node-card--${definition.category}${disabled ? ' node-card--disabled' : ''}`}>
      <span className="node-card__panel">
        <CategoryIcon category={definition.category} nodeType={definition.type} />
      </span>
      <button
        type="button"
        className="node-card__add"
        draggable={!disabled}
        disabled={disabled}
        onDragStart={onDragStart}
        onClick={() => onAdd(definition.type)}
        title={`${definition.description}\nClick or drag onto the canvas to add.`}
      >
        <span className="node-card__title">{definition.title}</span>
        <span className="node-card__description">{definition.description}</span>
      </button>
      {definition.help && <HelpButton definition={definition} className="node-card__help" />}
    </div>
  )
}
