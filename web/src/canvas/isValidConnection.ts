// Instant connection checks while drawing an edge. The server validator stays the authority; these
// rules refuse what it would report as an error (plan1.txt T8).
import type { Edge } from '@xyflow/react'
import { typeCompat, type Compat } from '../lib/compat'
import { expandOutputs } from '../lib/graphMapping'
import type { FlowEdge, FlowNode, NodeDefinition, Port } from '../types'

export type Refusal =
  | 'self_loop'
  | 'unknown_port'
  | 'incompatible_types'
  | 'duplicate'
  | 'fan_in'
  | 'fan_out'
  | 'cycle'

export type ConnectionCheck =
  | { ok: true; compat: Exclude<Compat, 'blocked'> }
  | { ok: false; reason: Refusal; message: string }

export interface GraphContext {
  nodes: FlowNode[]
  edges: FlowEdge[]
  catalog: Record<string, NodeDefinition>
}

/** A Connection or an Edge: React Flow passes either to isValidConnection. */
export interface Link {
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
}

function refuse(reason: Refusal, message: string): ConnectionCheck {
  return { ok: false, reason, message }
}

function findPorts(link: Link, ctx: GraphContext): { out?: Port; in?: Port; maxFanOut: number } {
  const source = ctx.nodes.find((n) => n.id === link.source)
  const target = ctx.nodes.find((n) => n.id === link.target)
  const sourceDef = source && ctx.catalog[source.data.nodeType]
  const targetDef = target && ctx.catalog[target.data.nodeType]
  return {
    out: sourceDef && expandOutputs(sourceDef, source.data.params).find((p) => p.id === link.sourceHandle),
    in: targetDef?.inputs.find((p) => p.id === link.targetHandle),
    maxFanOut: sourceDef?.maxFanOut ?? 4,
  }
}

/** True if `to` can already reach `from` along existing edges, so from -> to would close a loop. */
function reaches(from: string, to: string, edges: FlowEdge[]): boolean {
  const next = new Map<string, string[]>()
  for (const e of edges) next.set(e.source, [...(next.get(e.source) ?? []), e.target])
  const seen = new Set<string>()
  const stack = [to]
  while (stack.length > 0) {
    const node = stack.pop()!
    if (node === from) return true
    if (seen.has(node)) continue
    seen.add(node)
    stack.push(...(next.get(node) ?? []))
  }
  return false
}

export function checkConnection(link: Link, ctx: GraphContext): ConnectionCheck {
  if (link.source === link.target) {
    return refuse('self_loop', 'A node cannot connect to itself.')
  }
  const ports = findPorts(link, ctx)
  if (!ports.out || !ports.in) {
    return refuse('unknown_port', 'That port does not exist.')
  }
  const compat = typeCompat(ports.out.type, ports.in.type)
  if (compat === 'blocked') {
    return refuse('incompatible_types', `${ports.out.type} output cannot feed a ${ports.in.type} input.`)
  }
  const sameLink = (e: Edge) =>
    e.source === link.source && e.sourceHandle === link.sourceHandle &&
    e.target === link.target && e.targetHandle === link.targetHandle
  if (ctx.edges.some(sameLink)) {
    return refuse('duplicate', 'These ports are already connected.')
  }
  if (!ports.in.multi && ctx.edges.some((e) => e.target === link.target && e.targetHandle === link.targetHandle)) {
    return refuse('fan_in', `Input "${ports.in.label}" accepts one connection.`)
  }
  const fanOut = ctx.edges.filter((e) => e.source === link.source && e.sourceHandle === link.sourceHandle).length
  if (fanOut >= ports.maxFanOut) {
    return refuse('fan_out', `Output "${ports.out.label}" already has ${fanOut} connections (limit ${ports.maxFanOut}).`)
  }
  if (reaches(link.source, link.target, ctx.edges)) {
    return refuse('cycle', 'This connection would create a loop.')
  }
  return { ok: true, compat }
}
