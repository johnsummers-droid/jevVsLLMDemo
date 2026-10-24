// Graph (wire format) <-> React Flow nodes/edges, and the dynamic branch-port expansion.
import type { FlowEdge, FlowNode, Graph, NodeDefinition, Port } from '../types'

/**
 * Output ports for a node with these params; mirror of registry.expand_outputs on the server.
 *
 * Each dynamic template port ("route.*", dynamicFromParam="allowed_intents") becomes one branch
 * port per selected value, in the order selected, at the template's position. Missing params
 * fall back to their defaults; values are not checked here (the server validator does that).
 */
export function expandOutputs(definition: NodeDefinition, params: Record<string, unknown> = {}): Port[] {
  const ports: Port[] = []
  for (const port of definition.outputs) {
    if (!port.dynamicFromParam) {
      ports.push(port)
      continue
    }
    const prefix = port.id.replace(/\*$/, '')
    for (const value of selectedValues(definition, params, port.dynamicFromParam)) {
      ports.push({ ...port, id: prefix + value, label: branchLabel(value), dynamicFromParam: null })
    }
  }
  const ids = ports.map((p) => p.id)
  if (new Set(ids).size !== ids.length) {
    throw new Error(`${definition.type}: expanded output ids collide: ${ids.join(', ')}`)
  }
  return ports
}

function selectedValues(definition: NodeDefinition, params: Record<string, unknown>, key: string): string[] {
  const value = key in params ? params[key] : definition.params.find((spec) => spec.key === key)?.default
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

/** Same as Python's value.replace("_", " ").capitalize(). */
function branchLabel(value: string): string {
  const spaced = value.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase()
}

/** React Flow node type for a graph node: its catalog category, or "unknown" if not in the catalog. */
export function flowNodeType(nodeType: string, catalog: Record<string, NodeDefinition>): string {
  return catalog[nodeType]?.category ?? 'unknown'
}

export function graphToFlow(
  graph: Graph,
  catalog: Record<string, NodeDefinition>,
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  return {
    nodes: graph.nodes.map((node) => ({
      id: node.id,
      type: flowNodeType(node.type, catalog),
      position: { x: node.position.x, y: node.position.y },
      data: { nodeType: node.type, params: node.params, label: node.label },
    })),
    edges: graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      sourceHandle: edge.sourcePort,
      target: edge.target,
      targetHandle: edge.targetPort,
    })),
  }
}

export function flowToGraph(nodes: FlowNode[], edges: FlowEdge[]): Graph {
  return {
    schemaVersion: 1,
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.data.nodeType,
      position: { x: node.position.x, y: node.position.y },
      params: node.data.params,
      label: node.data.label,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      sourcePort: edge.sourceHandle ?? '',
      target: edge.target,
      targetPort: edge.targetHandle ?? '',
    })),
  }
}

/** Edge id format used by the server fixtures: "<source>.<port>-><target>.<port>". */
export function edgeId(source: string, sourcePort: string, target: string, targetPort: string): string {
  return `${source}.${sourcePort}->${target}.${targetPort}`
}
