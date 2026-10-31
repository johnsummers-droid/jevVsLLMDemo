// The help panel (plan1.txt S2-S4, S8): non-modal, docked along the bottom of the canvas area,
// resizable from its top edge. Content comes from the catalog: the node's `help` plus what the
// definition already knows (ports, param defaults, cost model).
import { useEffect, useRef, type KeyboardEvent, type PointerEvent } from 'react'
import { costRows } from '../lib/costModel'
import { useCatalogStore } from '../store/catalogStore'
import { HELP_PANEL_ID, useHelpStore } from '../store/helpStore'
import type { HelpExample, NodeDefinition, NodeHelp, ParamSpec, Port } from '../types'

const CATEGORY_LABELS: Record<string, string> = {
  io: 'Input / output',
  jev: 'Jev decision',
  llm: 'LLM',
  tool: 'Tool',
  human: 'Human',
}
const RESIZE_STEP = 0.05

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'none'
  if (typeof value === 'boolean') return value ? 'on' : 'off'
  if (value === '' || value == null) return 'empty'
  return String(value)
}

function portFlags(port: Port, input: boolean): string {
  return [
    port.jsonSchemaRef ?? port.type,
    input && (port.required ? 'required' : 'optional'),
    port.multi && 'accepts several',
    port.branch && 'branch',
  ]
    .filter(Boolean)
    .join(' · ')
}

function PortTable({ ports, texts, input = false }: { ports: Port[]; texts: Record<string, string>; input?: boolean }) {
  return (
    <dl className="help-panel__terms">
      {ports.map((port) => (
        <div key={port.id}>
          <dt>
            {port.label} <code>{port.id.replace('*', '<intent>')}</code>
            <span className="help-panel__meta">{portFlags(port, input)}</span>
          </dt>
          <dd>{texts[port.id] ?? ''}</dd>
        </div>
      ))}
    </dl>
  )
}

function ParamTable({ params, texts }: { params: ParamSpec[]; texts: Record<string, string> }) {
  return (
    <dl className="help-panel__terms">
      {params.map((spec) => (
        <div key={spec.key}>
          <dt>
            {spec.label} <code>{spec.key}</code>
            <span className="help-panel__meta">default: {formatValue(spec.default)}</span>
          </dt>
          <dd>{texts[spec.key] ?? ''}</dd>
        </div>
      ))}
    </dl>
  )
}

// Text ports carry messages, shown as quotes; other values (enums, numbers, JSON) as values.
function OutputValue({ value, port }: { value: unknown; port?: Port }) {
  if (typeof value === 'string' && port?.type === 'text') return <blockquote className="help-panel__quote">{value}</blockquote>
  if (value !== null && typeof value === 'object') return <pre className="help-panel__json">{JSON.stringify(value, null, 2)}</pre>
  return <code>{String(value)}</code>
}

function Example({ example, definition }: { example: HelpExample; definition: NodeDefinition }) {
  const labels = Object.fromEntries(
    [...definition.outputs, ...definition.params.map((p) => ({ id: p.key, label: p.label }))].map((p) => [p.id, p.label]),
  )
  const overrides = Object.entries(example.params ?? {})
  const outputs = Object.entries(example.outputs ?? {})
  const branchLabel = (id: string) => labels[id] ?? (id.startsWith('route.') ? 'Route' : id)
  // An expanded branch such as route.billing comes from the route.* template.
  const portOf = (id: string) =>
    definition.outputs.find((p) => p.id === id) ?? definition.outputs.find((p) => p.id === 'route.*' && id.startsWith('route.'))
  return (
    <div className="help-panel__example">
      <p className="help-panel__meta">
        Practice ticket {example.ticketId} ·{' '}
        {overrides.length
          ? `settings changed: ${overrides.map(([k, v]) => `${labels[k] ?? k} = ${formatValue(v)}`).join(', ')}`
          : 'default settings'}
      </p>
      {example.inputText != null && (
        <>
          <h4>Input</h4>
          <blockquote className="help-panel__quote">{example.inputText}</blockquote>
        </>
      )}
      <h4>Output</h4>
      {example.firedBranch && (
        <p>
          Branch taken: <code>{example.firedBranch}</code>
        </p>
      )}
      <dl className="help-panel__terms">
        {outputs.map(([id, value]) => (
          <div key={id}>
            <dt>
              {branchLabel(id)} <code>{id}</code>
            </dt>
            <dd>
              <OutputValue value={value} port={portOf(id)} />
            </dd>
          </div>
        ))}
      </dl>
      <p>{example.explanation}</p>
    </div>
  )
}

// Two columns, stacking on a narrow canvas: the explanation (with the example) on the left, the
// reference (ports, settings, cost) on the right.
function HelpContent({ definition, help }: { definition: NodeDefinition; help: NodeHelp }) {
  return (
    <div className="help-panel__body">
      <div className="help-panel__column">
        <section>
          <h3>What it is</h3>
          <p>{help.summary}</p>
          <h3>Where it goes</h3>
          <p>{help.placement}</p>
        </section>
        <section>
          <h3>How it works</h3>
          <ul>
            {help.howItWorks.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </section>
        {help.example && (
          <section>
            <h3>Example</h3>
            <Example example={help.example} definition={definition} />
          </section>
        )}
        {(help.tips ?? []).length > 0 && (
          <section>
            <h3>Tips</h3>
            <ul>
              {(help.tips ?? []).map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
      <div className="help-panel__column">
        {definition.inputs.length > 0 && (
          <section>
            <h3>Inputs</h3>
            <PortTable ports={definition.inputs} texts={help.inputs ?? {}} input />
          </section>
        )}
        {definition.params.length > 0 && (
          <section>
            <h3>Settings</h3>
            <ParamTable params={definition.params} texts={help.params ?? {}} />
          </section>
        )}
        {definition.outputs.length > 0 && (
          <section>
            <h3>Outputs</h3>
            <PortTable ports={definition.outputs} texts={help.outputs ?? {}} />
          </section>
        )}
        <section>
          <h3>Cost and speed</h3>
          <dl className="help-panel__costs">
            {costRows(definition.costModel).map(([term, detail]) => (
              <div key={term}>
                <dt>{term}</dt>
                <dd>{detail}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </div>
  )
}

export function HelpPanel() {
  const nodeType = useHelpStore((s) => s.nodeType)
  const height = useHelpStore((s) => s.height)
  const close = useHelpStore((s) => s.close)
  const setHeight = useHelpStore((s) => s.setHeight)
  const definition = useCatalogStore((s) => (nodeType ? s.byType[nodeType] : undefined))
  const headingRef = useRef<HTMLHeadingElement>(null)
  const panelRef = useRef<HTMLElement>(null)

  // Opening (or swapping) moves focus to the heading; close() returns it to the opener.
  useEffect(() => {
    if (nodeType) headingRef.current?.focus()
  }, [nodeType])

  // Esc closes, except while typing. Captured, because canvas nodes stop key propagation.
  useEffect(() => {
    if (!nodeType) return
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape' && !isEditable(event.target)) close()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [nodeType, close])

  if (!nodeType || !definition?.help) return null

  const area = () => panelRef.current?.parentElement?.getBoundingClientRect()
  const onResizeStart = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    const handle = event.currentTarget
    handle.setPointerCapture?.(event.pointerId)
    const move = (e: globalThis.PointerEvent) => {
      const rect = area()
      if (rect && rect.height > 0) setHeight((rect.bottom - e.clientY) / rect.height)
    }
    const end = () => {
      handle.removeEventListener('pointermove', move)
      handle.removeEventListener('pointerup', end)
      handle.removeEventListener('pointercancel', end)
    }
    handle.addEventListener('pointermove', move)
    handle.addEventListener('pointerup', end)
    handle.addEventListener('pointercancel', end)
  }
  const onResizeKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = { ArrowUp: RESIZE_STEP, ArrowDown: -RESIZE_STEP }[event.key]
    if (step === undefined) return
    event.preventDefault()
    setHeight(height + step)
  }

  return (
    <aside
      ref={panelRef}
      id={HELP_PANEL_ID}
      className={`help-panel help-panel--${definition.category}`}
      role="complementary"
      aria-label={`Help: ${definition.title}`}
    >
      <div
        className="help-panel__resize"
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize help panel"
        aria-valuemin={10}
        aria-valuemax={80}
        aria-valuenow={Math.round(height * 100)}
        tabIndex={0}
        onPointerDown={onResizeStart}
        onKeyDown={onResizeKey}
      />
      <header className="help-panel__header">
        <span className="help-panel__category">{CATEGORY_LABELS[definition.category] ?? definition.category}</span>
        <h2 ref={headingRef} tabIndex={-1}>
          {definition.title}
        </h2>
        <button type="button" className="help-panel__close" aria-label="Close help" onClick={close}>
          ×
        </button>
      </header>
      <HelpContent definition={definition} help={definition.help} />
    </aside>
  )
}
