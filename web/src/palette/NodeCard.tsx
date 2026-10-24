import type { DragEvent } from 'react'
import type { NodeDefinition } from '../types'

/** dataTransfer type for a palette drag; the canvas reads the node type from it on drop. */
export const NODE_DRAG_TYPE = 'application/x-pipeline-node'

interface NodeCardProps {
  definition: NodeDefinition
  onAdd: (nodeType: string) => void
}

export function NodeCard({ definition, onAdd }: NodeCardProps) {
  const onDragStart = (event: DragEvent) => {
    event.dataTransfer.setData(NODE_DRAG_TYPE, definition.type)
    event.dataTransfer.effectAllowed = 'move'
  }
  return (
    <button
      type="button"
      className={`node-card node-card--${definition.category}`}
      draggable
      onDragStart={onDragStart}
      onClick={() => onAdd(definition.type)}
      title={`${definition.description}\nClick or drag onto the canvas to add.`}
    >
      <span className="node-card__title">{definition.title}</span>
      <span className="node-card__description">{definition.description}</span>
    </button>
  )
}
