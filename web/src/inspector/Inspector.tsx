// Details of the selected node: params (editable), ports with types and payload schemas, and the
// cost/latency assumptions from its CostModel.
import { useMemo } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { HelpButton } from '../help/HelpButton'
import { costRows } from '../lib/costModel'
import { isHiddenParam } from '../lib/params'
import { portDescription, visibleInputs, visibleOutputs } from '../lib/ports'
import { countBySeverity } from '../lib/issues'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { useReadOnly } from '../store/runStore'
import { useValidationStore } from '../store/validationStore'
import type { NodeDefinition, Port } from '../types'
import { IssueList } from './IssueList'
import { ParamField } from './ParamField'

function PortItem({ definition, port, input = false }: { definition: NodeDefinition; port: Port; input?: boolean }) {
  return (
    <li className="inspector__port">
      <div className="inspector__port-name">
        <span className={`inspector__swatch typed-handle--${port.type}`} aria-hidden="true" />
        <span>{port.label}</span>
      </div>
      <p className="inspector__port-text">{portDescription(definition, port, input)}</p>
    </li>
  )
}

function NodeDetails({ nodeId, definition }: { nodeId: string; definition: NodeDefinition }) {
  const node = useGraphStore((s) => s.nodes.find((n) => n.id === nodeId))
  const updateParam = useGraphStore((s) => s.updateParam)
  const deleteNode = useGraphStore((s) => s.deleteNode)
  const locked = useReadOnly()
  const params = node?.data.params
  const index = useValidationStore((s) => s.index)
  const edges = useGraphStore((s) => s.edges)
  const inputs = useMemo(
    () => visibleInputs(definition, new Set(edges.filter((e) => e.target === nodeId).map((e) => e.targetHandle ?? ''))),
    [definition, edges, nodeId],
  )
  const outputs = useMemo(
    () => visibleOutputs(definition, params, new Set(edges.filter((e) => e.source === nodeId).map((e) => e.sourceHandle ?? ''))),
    [definition, params, edges, nodeId],
  )
  const issues = useMemo(
    () => [
      ...(index.byNode[nodeId] ?? []),
      ...edges.filter((e) => e.source === nodeId || e.target === nodeId).flatMap((e) => index.byEdge[e.id] ?? []),
    ],
    [index, edges, nodeId],
  )
  if (!node) return null
  const shownParams = definition.params.filter((spec) => !isHiddenParam(spec))

  return (
    <>
      <header className="inspector__header">
        <span className={`inspector__category inspector__category--${definition.category}`}>{definition.category}</span>
        <div className="inspector__title">
          <h2>{definition.title}</h2>
          {definition.help && <HelpButton definition={definition} />}
        </div>
        <p>{definition.description}</p>
      </header>

      {issues.length > 0 && (
        <section className="inspector__section">
          <h3>Issues</h3>
          <IssueList issues={issues} />
        </section>
      )}

      {shownParams.length > 0 && (
        <section className="inspector__section">
          <h3>Parameters</h3>
          {/* A disabled fieldset disables every control inside it. */}
          <fieldset className="inspector__params" disabled={locked}>
            {shownParams.map((spec) => (
              <ParamField
                key={`${node.id}:${spec.key}`}
                spec={spec}
                value={params?.[spec.key] ?? spec.default}
                onChange={(value) => updateParam(node.id, spec.key, value)}
              />
            ))}
          </fieldset>
        </section>
      )}

      <section className="inspector__section">
        <h3>Inputs</h3>
        {inputs.length ? (
          <ul className="inspector__ports">{inputs.map((p) => <PortItem key={p.id} definition={definition} port={p} input />)}</ul>
        ) : (
          <p className="inspector__empty">None (entry point)</p>
        )}
      </section>

      <section className="inspector__section">
        <h3>Outputs</h3>
        {outputs.length ? (
          <ul className="inspector__ports">{outputs.map((p) => <PortItem key={p.id} definition={definition} port={p} />)}</ul>
        ) : (
          <p className="inspector__empty">None (exit point)</p>
        )}
      </section>

      {outputs.length > 0 && (
        <section className="inspector__section">
          <h3>Notes</h3>
          <p className="inspector__note">Each output can feed up to {definition.maxFanOut ?? 4} connections.</p>
        </section>
      )}

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

      {!locked && (
        <button type="button" className="inspector__delete" onClick={() => deleteNode(node.id)}>
          Delete node
        </button>
      )}
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
