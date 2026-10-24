import { describe, expect, it } from 'vitest'
import catalogFixture from '../../../shared/fixtures/catalog.json'
import expandedFixture from '../../../shared/fixtures/expanded-outputs.json'
import defaultGraph from '../../../shared/fixtures/graphs/default.json'
import strongGraph from '../../../shared/fixtures/graphs/strong.json'
import weakGraph from '../../../shared/fixtures/graphs/weak.json'
import type { CatalogResponse, Graph, NodeDefinition, Port } from '../types'
import { edgeId, expandOutputs, flowToGraph, graphToFlow } from './graphMapping'

const catalog = (catalogFixture as CatalogResponse).nodes
const byType: Record<string, NodeDefinition> = Object.fromEntries(catalog.map((d) => [d.type, d]))
const graphs = {
  default: defaultGraph as Graph,
  weak: weakGraph as Graph,
  strong: strongGraph as Graph,
}
const expanded = expandedFixture.graphs as Record<string, Record<string, Port[]>>
const graphNames = Object.keys(graphs) as (keyof typeof graphs)[]

describe('graphToFlow / flowToGraph', () => {
  it.each(graphNames)('round-trips the %s graph losslessly', (name) => {
    const { nodes, edges } = graphToFlow(graphs[name], byType)
    expect(flowToGraph(nodes, edges)).toEqual(graphs[name])
  })

  it.each(graphNames)('gives every %s node its catalog category and keeps port ids as handles', (name) => {
    const graph = graphs[name]
    const { nodes, edges } = graphToFlow(graph, byType)
    expect(nodes.map((n) => n.type)).toEqual(graph.nodes.map((n) => byType[n.type].category))
    expect(edges.map((e) => [e.sourceHandle, e.targetHandle])).toEqual(
      graph.edges.map((e) => [e.sourcePort, e.targetPort]),
    )
  })

  it('maps a node type missing from the catalog to "unknown"', () => {
    const graph: Graph = {
      schemaVersion: 1,
      nodes: [{ id: 'x', type: 'no_such_node', position: { x: 1, y: 2 } }],
      edges: [],
    }
    const { nodes, edges } = graphToFlow(graph, byType)
    expect(nodes[0].type).toBe('unknown')
    expect(flowToGraph(nodes, edges)).toEqual(graph)
  })
})

describe('expandOutputs', () => {
  it.each(graphNames)("matches the server's expansion for every %s node", (name) => {
    for (const node of graphs[name].nodes) {
      expect(expandOutputs(byType[node.type], node.params), node.id).toEqual(expanded[name][node.id])
    }
  })

  it.each(graphNames)('offers every source port used by a %s edge', (name) => {
    for (const edge of graphs[name].edges) {
      const ids = expanded[name][edge.source].map((p) => p.id)
      expect(ids).toContain(edge.sourcePort)
    }
  })

  it('falls back to the param default when the param is missing', () => {
    const router = byType.jev_intent_router
    const spec = router.params.find((p) => p.key === 'allowed_intents')
    expect(spec?.kind).toBe('multi_enum')
    const branches = expandOutputs(router).filter((p) => p.id.startsWith('route.'))
    expect(branches.map((p) => p.id)).toEqual([
      ...(spec?.default as string[]).map((v) => `route.${v}`),
      'route.low_confidence',
    ])
    expect(branches.every((p) => p.dynamicFromParam === null)).toBe(true)
  })

  it('labels branches like Python str.capitalize', () => {
    const router = byType.jev_intent_router
    const ports = expandOutputs(router, { allowed_intents: ['technical_support', 'BUG_Report'] })
    expect(ports.find((p) => p.id === 'route.technical_support')?.label).toBe('Technical support')
    expect(ports.find((p) => p.id === 'route.BUG_Report')?.label).toBe('Bug report')
  })

  it('refuses expansions whose port ids collide', () => {
    const router = byType.jev_intent_router
    expect(() => expandOutputs(router, { allowed_intents: ['billing', 'billing'] })).toThrow(/collide/)
  })
})

describe('edgeId', () => {
  it.each(graphNames)('reproduces the %s fixture edge ids', (name) => {
    for (const e of graphs[name].edges) {
      expect(edgeId(e.source, e.sourcePort, e.target, e.targetPort)).toBe(e.id)
    }
  })
})
