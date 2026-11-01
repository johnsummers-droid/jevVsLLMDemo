// The catalog in collapsible sections, one per category. Click a card to add it at the canvas
// center, or drag it.
import { useState } from 'react'
import { CategoryIcon } from '../nodes/CategoryIcon'
import type { NodeCategory, NodeDefinition } from '../types'
import { NodeCard } from './NodeCard'

const GROUPS: { category: NodeCategory; title: string }[] = [
  { category: 'jev', title: 'Jev decision nodes' },
  { category: 'llm', title: 'LLM generation nodes' },
  { category: 'tool', title: 'Deterministic tools' },
  { category: 'human', title: 'Human review' },
  { category: 'io', title: 'Customer' },
]

interface PaletteProps {
  nodes: NodeDefinition[]
  onAdd: (nodeType: string) => void
  /** Read-only graph: the cards can't be clicked or dragged. */
  disabled?: boolean
}

export function Palette({ nodes, onAdd, disabled = false }: PaletteProps) {
  const [collapsed, setCollapsed] = useState<ReadonlySet<NodeCategory>>(new Set())
  const toggle = (category: NodeCategory) =>
    setCollapsed((current) => {
      const next = new Set(current)
      if (!next.delete(category)) next.add(category)
      return next
    })
  return (
    <aside className="palette" aria-label="Node palette">
      {GROUPS.map(({ category, title }) => {
        const members = nodes.filter((n) => n.category === category)
        if (members.length === 0) return null
        const open = !collapsed.has(category)
        return (
          <section key={category} className={`palette__group palette__group--${category}`}>
            <h2 className="palette__heading">
              <button type="button" className="palette__toggle" aria-expanded={open} onClick={() => toggle(category)}>
                <CategoryIcon category={category} className="palette__icon" />
                {title}
                <svg className="palette__chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
                  <path d="m5 9 7 7 7-7" />
                </svg>
              </button>
            </h2>
            {open && (
              <div className="palette__cards">
                {members.map((definition) => (
                  <NodeCard key={definition.type} definition={definition} onAdd={onAdd} disabled={disabled} />
                ))}
              </div>
            )}
          </section>
        )
      })}
    </aside>
  )
}
