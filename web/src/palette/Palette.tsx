// The catalog, grouped by category. Click a card to add it at the canvas center, or drag it.
import type { NodeCategory, NodeDefinition } from '../types'
import { NodeCard } from './NodeCard'

const GROUPS: { category: NodeCategory; title: string }[] = [
  { category: 'io', title: 'Input / output' },
  { category: 'jev', title: 'Jev' },
  { category: 'llm', title: 'LLM' },
  { category: 'tool', title: 'Tools' },
  { category: 'human', title: 'Human' },
]

interface PaletteProps {
  nodes: NodeDefinition[]
  onAdd: (nodeType: string) => void
  /** Read-only graph: the cards can't be clicked or dragged. */
  disabled?: boolean
}

export function Palette({ nodes, onAdd, disabled = false }: PaletteProps) {
  return (
    <aside className="palette" aria-label="Node palette">
      {GROUPS.map(({ category, title }) => {
        const members = nodes.filter((n) => n.category === category)
        if (members.length === 0) return null
        return (
          <section key={category} className="palette__group">
            <h2 className="palette__heading">{title}</h2>
            {members.map((definition) => (
              <NodeCard key={definition.type} definition={definition} onAdd={onAdd} disabled={disabled} />
            ))}
          </section>
        )
      })}
    </aside>
  )
}
