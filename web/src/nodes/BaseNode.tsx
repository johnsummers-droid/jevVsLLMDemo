// Shared node body: header, then one row per input (left) and output (right) with typed handles.
// Output handles follow the params, so a router shows one branch handle per allowed intent.
import { useUpdateNodeInternals, type NodeProps } from '@xyflow/react'
import { useEffect, useMemo, type ReactNode } from 'react'
import { TypedHandle } from '../handles/TypedHandle'
import { expandOutputs } from '../lib/graphMapping'
import { useCatalogStore } from '../store/catalogStore'
import type { FlowNode, NodeCategory, Port } from '../types'

const CATEGORY_LABELS: Record<NodeCategory, string> = {
  io: 'Input / output',
  jev: 'Jev decision',
  llm: 'LLM',
  tool: 'Tool',
  human: 'Human',
}

interface BaseNodeProps extends NodeProps<FlowNode> {
  category: NodeCategory | 'unknown'
  /** Optional extra line under the title (category components use it). */
  children?: ReactNode
}

function PortRow({ port, kind }: { port: Port; kind: 'source' | 'target' }) {
  const classes = ['port', `port--${kind}`, port.branch ? 'port--branch' : '', kind === 'target' && port.required ? 'port--required' : '']
  return (
    <div className={classes.filter(Boolean).join(' ')}>
      <TypedHandle port={port} kind={kind} />
      <span className="port__label">{port.label}</span>
      <span className="port__type">{port.type}</span>
    </div>
  )
}

export function BaseNode({ id, data, selected, category, children }: BaseNodeProps) {
  const definition = useCatalogStore((s) => s.byType[data.nodeType])
  const outputs = useMemo(() => (definition ? expandOutputs(definition, data.params) : []), [definition, data.params])
  const outputKey = outputs.map((p) => p.id).join('|')
  const updateNodeInternals = useUpdateNodeInternals()
  useEffect(() => updateNodeInternals(id), [id, outputKey, updateNodeInternals])

  return (
    <div className={`pipeline-node pipeline-node--${category}${selected ? ' pipeline-node--selected' : ''}`}>
      <header className="pipeline-node__header">
        <span className="pipeline-node__category">
          {category === 'unknown' ? 'Unknown' : CATEGORY_LABELS[category]}
        </span>
        <strong className="pipeline-node__title">{data.label || definition?.title || data.nodeType}</strong>
        <span className="pipeline-node__id">{id}</span>
        {children}
      </header>
      {definition ? (
        <div className="pipeline-node__ports">
          <div className="pipeline-node__inputs">
            {definition.inputs.map((port) => (
              <PortRow key={port.id} port={port} kind="target" />
            ))}
          </div>
          <div className="pipeline-node__outputs">
            {outputs.map((port) => (
              <PortRow key={port.id} port={port} kind="source" />
            ))}
          </div>
        </div>
      ) : (
        <p className="pipeline-node__missing">Node type “{data.nodeType}” is not in the catalog.</p>
      )}
    </div>
  )
}
