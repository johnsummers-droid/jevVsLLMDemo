import { describe, expect, it } from 'vitest'
import { catalogByType } from '../test/fixtures'
import type { FlowEdge, FlowNode, NodeDefinition } from '../types'
import { checkConnection, type GraphContext, type Link } from './isValidConnection'

// Test-only node with an "any" output; no MVP node has one.
const anySource: NodeDefinition = {
  ...catalogByType.knowledge_lookup,
  type: 'test_any_source',
  outputs: [{ id: 'value', label: 'Value', type: 'any' }],
}
const catalog: Record<string, NodeDefinition> = { ...catalogByType, test_any_source: anySource }

function node(id: string, nodeType: string, params: Record<string, unknown> = {}): FlowNode {
  return { id, type: catalog[nodeType].category, position: { x: 0, y: 0 }, data: { nodeType, params, label: null } }
}

function edge(source: string, sourceHandle: string, target: string, targetHandle: string): FlowEdge {
  return { id: `${source}.${sourceHandle}->${target}.${targetHandle}`, source, sourceHandle, target, targetHandle }
}

const nodes = [
  node('msg', 'customer_message'),
  node('router', 'jev_intent_router', { allowed_intents: ['billing', 'account'] }),
  node('llm', 'llm_answer_generator'),
  node('llm2', 'llm_answer_generator'),
  node('kb', 'knowledge_lookup'),
  node('kb2', 'knowledge_lookup'),
  node('human', 'human_review_queue'),
  node('reply', 'customer_response'),
  node('anything', 'test_any_source'),
]

function ctx(edges: FlowEdge[] = []): GraphContext {
  return { nodes, edges, catalog }
}

const link = (source: string, sourceHandle: string, target: string, targetHandle: string): Link => ({
  source,
  sourceHandle,
  target,
  targetHandle,
})

describe('checkConnection', () => {
  it('accepts a matching connection', () => {
    expect(checkConnection(link('msg', 'text', 'router', 'text'), ctx())).toEqual({ ok: true, compat: 'ok' })
  })

  it('accepts an expanded branch port', () => {
    expect(checkConnection(link('router', 'route.account', 'llm', 'text'), ctx()).ok).toBe(true)
  })

  it('accepts an "any" source with a warning', () => {
    expect(checkConnection(link('anything', 'value', 'llm', 'text'), ctx())).toEqual({ ok: true, compat: 'warn' })
  })

  it('accepts several edges into a multi input', () => {
    const edges = [edge('llm', 'text', 'reply', 'text')]
    expect(checkConnection(link('human', 'text', 'reply', 'text'), ctx(edges)).ok).toBe(true)
  })

  const refusals: [string, Link, FlowEdge[]][] = [
    ['self_loop', link('llm', 'text', 'llm', 'text'), []],
    ['unknown_port', link('router', 'route.billing_typo', 'llm', 'text'), []],
    ['unknown_port', link('msg', 'text', 'llm', 'nope'), []],
    ['unknown_port', link('ghost', 'text', 'llm', 'text'), []],
    ['incompatible_types', link('kb', 'docs', 'llm', 'text'), []],
    ['incompatible_types', link('msg', 'text', 'llm', 'context'), []],
    ['duplicate', link('msg', 'text', 'router', 'text'), [edge('msg', 'text', 'router', 'text')]],
    ['fan_in', link('kb2', 'docs', 'llm', 'context'), [edge('kb', 'docs', 'llm', 'context')]],
    [
      'fan_out',
      link('msg', 'text', 'reply', 'text'),
      [
        edge('msg', 'text', 'router', 'text'),
        edge('msg', 'text', 'llm', 'text'),
        edge('msg', 'text', 'llm2', 'text'),
        edge('msg', 'text', 'kb', 'text'),
      ],
    ],
    ['cycle', link('llm2', 'text', 'llm', 'text'), [edge('llm', 'text', 'human', 'text'), edge('human', 'text', 'llm2', 'text')]],
  ]

  it.each(refusals)('refuses with %s (%#)', (reason, candidate, edges) => {
    const check = checkConnection(candidate, ctx(edges))
    expect(check).toMatchObject({ ok: false, reason })
    expect(check.ok || check.message.length > 0).toBe(true)
  })

  it('covers every refusal reason', () => {
    expect(new Set(refusals.map(([reason]) => reason))).toEqual(
      new Set(['self_loop', 'unknown_port', 'incompatible_types', 'duplicate', 'fan_in', 'fan_out', 'cycle']),
    )
  })

  it('counts fan-out per output port, not per node', () => {
    const edges = ['router', 'llm', 'llm2', 'kb'].map((t) => edge('msg', 'text', t, 'text'))
    expect(checkConnection(link('msg', 'meta', 'llm', 'context'), ctx(edges)).ok).toBe(true)
  })
})
