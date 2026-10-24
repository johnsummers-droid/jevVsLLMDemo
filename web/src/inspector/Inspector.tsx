// Details of the selected node: params (editable), ports with types and payload schemas, and the
// cost/latency assumptions from its CostModel.
import { useMemo } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { expandOutputs } from '../lib/graphMapping'
import { countBySeverity } from '../lib/issues'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { useValidationStore } from '../store/validationStore'
import type { CostModel, NodeDefinition, Port } from '../types'
import { IssueList } from './IssueList'
import { ParamField } from './ParamField'
import { SchemaPreview } from './SchemaPreview'

function PortItem({ port, input = false }: { port: Port; input?: boolean }) {
  const flags = [input && port.required && 'required', port.multi && 'accepts several', port.branch && 'branch'].filter(Boolean)
  return (
    <li className="inspector__port">
      <span className={`inspector__swatch typed-handle--${port.type}`} aria-hidden="true" />
      <span>{port.label}</span>
      <code className="inspector__port-type">{port.jsonSchemaRef ?? port.type}</code>
      {flags.length > 0 && <span className="inspector__flags">{flags.join(', ')}</span>}
      {port.jsonSchemaRef && <SchemaPreview name={port.jsonSchemaRef} />}
    </li>
  )
}

const usd = (n: number) => `$${n < 0.01 && n > 0 ? n.toPrecision(2) : n.toFixed(2)}`

function costRows(cost: CostModel): [string, string][] {
  const rows: [string, string][] = []
  const jitter = cost.latencyJitterMs ? ` ± ${cost.latencyJitterMs} ms` : ''
  const latency = cost.latencyMs >= 1000 ? `${cost.latencyMs / 1000} s` : `${cost.latencyMs} ms`
  rows.push(['Latency', `${latency}${jitter}`])
  if (cost.perTokenLatencyMs) rows.push(['Per output token', `+ ${cost.perTokenLatencyMs} ms`])
  rows.push(['Cost per call', usd(cost.costPerCallUsd ?? 0)])
  if (cost.priceInPer1KUsd != null) rows.push(['Input price', `${usd(cost.priceInPer1KUsd)} / 1k tokens`])
  if (cost.priceOutPer1KUsd != null) rows.push(['Output price', `${usd(cost.priceOutPer1KUsd)} / 1k tokens`])
  if (cost.excludedFromLatency) rows.push(['Latency metrics', 'not counted in p95 latency'])
  return rows
}

function NodeDetails({ nodeId, definition }: { nodeId: string; definition: NodeDefinition }) {
  const node = useGraphStore((s) => s.nodes.find((n) => n.id === nodeId))
  const updateParam = useGraphStore((s) => s.updateParam)
  const deleteNode = useGraphStore((s) => s.deleteNode)
  const params = node?.data.params
  const outputs = useMemo(() => expandOutputs(definition, params), [definition, params])
  const index = useValidationStore((s) => s.index)
  const edges = useGraphStore((s) => s.edges)
  const issues = useMemo(
    () => [
      ...(index.byNode[nodeId] ?? []),
      ...edges.filter((e) => e.source === nodeId || e.target === nodeId).flatMap((e) => index.byEdge[e.id] ?? []),
    ],
    [index, edges, nodeId],
  )
  if (!node) return null

  return (
    <>
      <header className="inspector__header">
        <span className={`inspector__category inspector__category--${definition.category}`}>{definition.category}</span>
        <h2>{definition.title}</h2>
        <code>{node.id}</code>
        <p>{definition.description}</p>
      </header>

      {issues.length > 0 && (
        <section className="inspector__section">
          <h3>Issues</h3>
          <IssueList issues={issues} />
        </section>
      )}

      {definition.params.length > 0 && (
        <section className="inspector__section">
          <h3>Parameters</h3>
          {definition.params.map((spec) => (
            <ParamField
              key={`${node.id}:${spec.key}`}
              spec={spec}
              value={params?.[spec.key] ?? spec.default}
              onChange={(value) => updateParam(node.id, spec.key, value)}
            />
          ))}
        </section>
      )}

      <section className="inspector__section">
        <h3>Inputs</h3>
        {definition.inputs.length ? (
          <ul className="inspector__ports">{definition.inputs.map((p) => <PortItem key={p.id} port={p} input />)}</ul>
        ) : (
          <p className="inspector__empty">None (entry point)</p>
        )}
        <h3>Outputs</h3>
        {outputs.length ? (
          <ul className="inspector__ports">{outputs.map((p) => <PortItem key={p.id} port={p} />)}</ul>
        ) : (
          <p className="inspector__empty">None (exit point)</p>
        )}
        <p className="inspector__note">Each output can feed up to {definition.maxFanOut ?? 4} connections.</p>
      </section>

      <section className="inspector__section">
        <h3>Cost and latency assumptions</h3>
        <dl className="inspector__costs">
          {costRows(definition.costModel).map(([term, detail]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{detail}</dd>
            </div>
          ))}
        </dl>
      </section>

      <button type="button" className="inspector__delete" onClick={() => deleteNode(node.id)}>
        Delete node
      </button>
    </>
  )
}

function GraphIssues() {
  const status = useValidationStore((s) => s.status)
  const report = useValidationStore((s) => s.report)
  const error = useValidationStore((s) => s.error)
  const counts = countBySeverity(report?.issues ?? [])
  let summary = 'Checking…'
  if (status === 'error') summary = `Validation unavailable: ${error}`
  else if (report && status !== 'pending') {
    summary = report.issues.length === 0 ? 'No issues found.' : `${counts.error} errors, ${counts.warning} warnings`
  }
  return (
    <section className="inspector__section inspector__section--first">
      <h3>Pipeline check</h3>
      <p className="inspector__note" role="status">
        {summary}
      </p>
      {report && <IssueList issues={report.issues} emptyText="" />}
    </section>
  )
}

export function Inspector() {
  const selected = useGraphStore(useShallow((s) => s.nodes.filter((n) => n.selected)))
  const catalog = useCatalogStore((s) => s.byType)
  const only = selected.length === 1 ? selected[0] : null
  const definition = only ? catalog[only.data.nodeType] : undefined

  return (
    <aside className="inspector" aria-label="Inspector">
      {!only && (
        <>
          <p className="inspector__empty">
            {selected.length > 1 ? `${selected.length} nodes selected.` : 'Select a node to see and edit its settings.'}
          </p>
          <GraphIssues />
        </>
      )}
      {only && !definition && (
        <p className="inspector__empty">Node type “{only.data.nodeType}” is not in the catalog.</p>
      )}
      {only && definition && <NodeDetails key={only.id} nodeId={only.id} definition={definition} />}
    </aside>
  )
}
