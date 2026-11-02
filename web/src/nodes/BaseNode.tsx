// Shared node body: header, then one row per input (left) and output (right) with typed handles.
// Output handles follow the params, so a router shows one branch handle per allowed intent.
import { useUpdateNodeInternals, type NodeProps } from '@xyflow/react'
import { useEffect, useMemo, type ReactNode } from 'react'
import { TypedHandle } from '../handles/TypedHandle'
import { HelpButton } from '../help/HelpButton'
import { CATEGORY_LABELS } from './categoryLabels'
import { CategoryIcon } from './CategoryIcon'
import { portKey, worstSeverity } from '../lib/issues'
import { visibleInputs, visibleOutputs } from '../lib/ports'
import { NodeStatsBadge } from '../run/NodeStatsBadge'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { useValidationStore } from '../store/validationStore'
import type { FlowNode, NodeCategory, Port } from '../types'

interface BaseNodeProps extends NodeProps<FlowNode> {
  category: NodeCategory | 'unknown'
  /** Optional extra line under the title (category components use it). */
  children?: ReactNode
}

function PortRow({ nodeId, port, kind }: { nodeId: string; port: Port; kind: 'source' | 'target' }) {
  const issues = useValidationStore((s) => s.index.byPort[portKey(nodeId, port.id)])
  const severity = worstSeverity(issues)
  const classes = [
    'port',
    `port--${kind}`,
    port.branch && 'port--branch',
    kind === 'target' && port.required && 'port--required',
    severity && `port--${severity}`,
  ]
  return (
    <div className={classes.filter(Boolean).join(' ')} title={issues?.map((i) => i.message).join('\n')}>
      <TypedHandle port={port} kind={kind} />
      <span className="port__label">{port.label}</span>
      <span className="port__type">{port.type}</span>
    </div>
  )
}

export function BaseNode({ id, data, selected, category, children }: BaseNodeProps) {
  const definition = useCatalogStore((s) => s.byType[data.nodeType])
  const issues = useValidationStore((s) => s.index.byNode[id])
  const severity = worstSeverity(issues)
  // A joined string, so that this node re-renders only when its own outgoing edges change.
  const connected = useGraphStore((s) => s.edges.filter((e) => e.source === id).map((e) => e.sourceHandle).join('|'))
  const connectedIn = useGraphStore((s) => s.edges.filter((e) => e.target === id).map((e) => e.targetHandle).join('|'))
  const inputs = useMemo(() => (definition ? visibleInputs(definition, new Set(connectedIn.split('|'))) : []), [definition, connectedIn])
  const outputs = useMemo(
    () => (definition ? visibleOutputs(definition, data.params, new Set(connected.split('|'))) : []),
    [definition, data.params, connected],
  )
  const outputKey = [...inputs, ...outputs].map((p) => p.id).join('|')
  const updateNodeInternals = useUpdateNodeInternals()
  useEffect(() => updateNodeInternals(id), [id, outputKey, updateNodeInternals])

  const categoryLabel = category === 'unknown' ? 'Unknown' : CATEGORY_LABELS[category]
  const badge = severity && issues && (
    <span
      className={`issue-badge issue-badge--${severity} issue-badge--node`}
      title={issues.map((i) => i.message).join('\n')}
      role="img"
      aria-label={`${issues.length} ${severity === 'error' ? 'error' : 'warning'}${issues.length > 1 ? 's' : ''} on this node`}
    >
      {severity === 'error' ? '!' : '⚠'} {issues.length}
    </span>
  )
  const title = data.label || definition?.title || data.nodeType
  const help = definition?.help && <HelpButton definition={definition} className="pipeline-node__help" />
  const ports = definition ? (
    <div className="pipeline-node__ports">
      <div className="pipeline-node__inputs">
        {inputs.map((port) => (
          <PortRow key={port.id} nodeId={id} port={port} kind="target" />
        ))}
      </div>
      <div className="pipeline-node__outputs">
        {outputs.map((port) => (
          <PortRow key={port.id} nodeId={id} port={port} kind="source" />
        ))}
      </div>
    </div>
  ) : (
    <p className="pipeline-node__missing">Node type “{data.nodeType}” is not in the catalog.</p>
  )

  return (
    <div
      className={[
        'pipeline-node',
        `pipeline-node--${category}`,
        selected && 'pipeline-node--selected',
        severity && `pipeline-node--${severity}`,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {badge}
      <header className="pipeline-node__header">
        <span className="pipeline-node__icon" title={categoryLabel}>
          <CategoryIcon category={category} nodeType={data.nodeType} alt={categoryLabel} />
        </span>
        <div className="pipeline-node__heading">
          <strong className="pipeline-node__title">{title}</strong>
          <span className="pipeline-node__id">{id}</span>
          {children}
        </div>
        {help}
      </header>
      {ports}
      <NodeStatsBadge nodeId={id} />
    </div>
  )
}
