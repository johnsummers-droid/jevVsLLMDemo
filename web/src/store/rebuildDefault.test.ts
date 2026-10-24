// M2 exit criterion: the default graph can be rebuilt from an empty canvas with the same store
// actions the UI uses, and the result matches shared/fixtures/graphs/default.json (ids and
// positions aside).
import { beforeEach, describe, expect, it } from 'vitest'
import { checkParam } from '../lib/params'
import { catalogByType, catalogNodes, defaultGraphFixture } from '../test/fixtures'
import type { Graph } from '../types'
import { useCatalogStore } from './catalogStore'
import { useGraphStore } from './graphStore'

const initialGraph = useGraphStore.getState()

beforeEach(() => {
  useCatalogStore.setState({ status: 'ready', nodes: catalogNodes, byType: catalogByType, error: null })
  useGraphStore.setState(initialGraph, true)
})

/** Nodes as {type, params, label} and edges as type.port -> type.port, sorted. */
function shape(graph: Graph) {
  const typeOf = Object.fromEntries(graph.nodes.map((n) => [n.id, n.type]))
  return {
    nodes: graph.nodes.map((n) => ({ type: n.type, params: n.params, label: n.label ?? null })).sort((a, b) => a.type.localeCompare(b.type)),
    edges: graph.edges.map((e) => `${typeOf[e.source]}.${e.sourcePort}->${typeOf[e.target]}.${e.targetPort}`).sort(),
  }
}

describe('rebuilding the default graph', () => {
  it('matches default.json', () => {
    const store = useGraphStore.getState()
    const ids: Record<string, string> = {}

    // Add each node, then set the params that differ from the catalog defaults, as the inspector would.
    defaultGraphFixture.nodes.forEach((node, i) => {
      const id = store.addNode(node.type, { x: i * 300, y: 0 })
      ids[node.id] = id
      const definition = catalogByType[node.type]
      for (const spec of definition.params) {
        const value = node.params?.[spec.key]
        if (JSON.stringify(value) === JSON.stringify(spec.default)) continue
        expect(checkParam(spec, value), `${node.id}.${spec.key}`).toBeNull()
        store.updateParam(id, spec.key, value)
      }
    })

    // Draw every edge; each must pass the canvas connection rules.
    for (const edge of defaultGraphFixture.edges) {
      const check = store.connect({
        source: ids[edge.source],
        sourceHandle: edge.sourcePort,
        target: ids[edge.target],
        targetHandle: edge.targetPort,
      })
      expect(check, edge.id).toMatchObject({ ok: true })
    }

    expect(shape(useGraphStore.getState().toGraph())).toEqual(shape(defaultGraphFixture))
  })
})
