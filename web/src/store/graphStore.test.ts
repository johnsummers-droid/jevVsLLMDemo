import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { catalogByType, catalogNodes, defaultGraphFixture } from '../test/fixtures'
import { useCatalogStore } from './catalogStore'
import { useGraphStore } from './graphStore'

const initialGraphState = useGraphStore.getState()
const store = () => useGraphStore.getState()

beforeEach(() => {
  useCatalogStore.setState({ status: 'ready', nodes: catalogNodes, byType: catalogByType, error: null })
  useGraphStore.setState(initialGraphState, true)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

const connection = (source: string, sourceHandle: string, target: string, targetHandle: string) => ({
  source,
  sourceHandle,
  target,
  targetHandle,
})

describe('graphStore', () => {
  it('loads the default graph from the server', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(defaultGraphFixture)))
    vi.stubGlobal('fetch', fetchMock)
    await Promise.all([store().loadDefault(), store().loadDefault()])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(store().status).toBe('ready')
    expect(store().toGraph()).toEqual(defaultGraphFixture)
  })

  it('records a failed load', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 500 })))
    await store().loadDefault()
    expect(store()).toMatchObject({ status: 'error', nodes: [] })
  })

  it('adds nodes with default params and unique ids', () => {
    expect(store().addNode('llm_answer_generator', { x: 1, y: 2 })).toBe('llm_answer_generator')
    expect(store().addNode('llm_answer_generator', { x: 3, y: 4 })).toBe('llm_answer_generator_2')
    const [first] = store().toGraph().nodes
    expect(first).toEqual({
      id: 'llm_answer_generator',
      type: 'llm_answer_generator',
      position: { x: 1, y: 2 },
      params: Object.fromEntries(catalogByType.llm_answer_generator.params.map((p) => [p.key, p.default])),
      label: null,
    })
    expect(store().nodes[0].type).toBe('llm')
  })

  it('nudges a node added on top of another', () => {
    store().addNode('customer_message', { x: 100, y: 100 })
    store().addNode('customer_message', { x: 100, y: 100 })
    store().addNode('customer_message', { x: 105, y: 95 })
    expect(store().nodes.map((n) => n.position)).toEqual([
      { x: 100, y: 100 },
      { x: 132, y: 132 },
      { x: 169, y: 159 },
    ])
  })

  it('does not share default param values between nodes', () => {
    const a = store().addNode('jev_intent_router', { x: 0, y: 0 })
    const b = store().addNode('jev_intent_router', { x: 0, y: 0 })
    const intents = (id: string) => store().nodes.find((n) => n.id === id)!.data.params!.allowed_intents
    expect(intents(a)).not.toBe(intents(b))
  })

  it('refuses an unknown node type', () => {
    expect(() => store().addNode('nope', { x: 0, y: 0 })).toThrow(/unknown node type/)
  })

  it('moves a node', () => {
    const id = store().addNode('customer_message', { x: 0, y: 0 })
    store().moveNode(id, { x: 50, y: 60 })
    expect(store().nodes[0].position).toEqual({ x: 50, y: 60 })
  })

  it('connects valid ports with the server edge id format and refuses invalid ones', () => {
    store().addNode('customer_message', { x: 0, y: 0 })
    store().addNode('jev_intent_router', { x: 0, y: 0 })
    expect(store().connect(connection('customer_message', 'text', 'jev_intent_router', 'text')).ok).toBe(true)
    expect(store().edges.map((e) => e.id)).toEqual(['customer_message.text->jev_intent_router.text'])

    const refused = store().connect(connection('jev_intent_router', 'route.billing', 'jev_intent_router', 'text'))
    expect(refused).toMatchObject({ ok: false, reason: 'self_loop' })
    expect(store().edges).toHaveLength(1)
  })

  it('deletes an edge', () => {
    store().setGraph(defaultGraphFixture)
    const [first, ...rest] = store().edges
    store().deleteEdge(first.id)
    expect(store().edges).toEqual(rest)
  })

  it('deletes a node with its edges', () => {
    store().setGraph(defaultGraphFixture)
    store().deleteNode('router')
    expect(store().nodes.some((n) => n.id === 'router')).toBe(false)
    expect(store().edges.some((e) => e.source === 'router' || e.target === 'router')).toBe(false)
    expect(store().edges.length).toBeGreaterThan(0)
  })

  it('drops the edges of nodes removed through React Flow changes', () => {
    store().setGraph(defaultGraphFixture)
    store().onNodesChange([{ type: 'remove', id: 'router' }])
    expect(store().edges.some((e) => e.source === 'router' || e.target === 'router')).toBe(false)
  })

  it('drops only the edges of branches a param change removes, with a notice', () => {
    store().setGraph(defaultGraphFixture)
    const before = store().edges.length
    const dropped = store().updateParam('router', 'allowed_intents', ['technical_support', 'bug_report'])
    expect(dropped).toEqual(['router.route.billing->llm.text', 'router.route.feature_request->llm.text'])
    expect(store().edges).toHaveLength(before - 2)
    expect(store().notice).toMatch(/Removed 2 connections/)
    expect(store().toGraph().nodes.find((n) => n.id === 'router')!.params!.allowed_intents).toEqual([
      'technical_support',
      'bug_report',
    ])
  })

  it('keeps edges when a param change does not touch branch ports', () => {
    store().setGraph(defaultGraphFixture)
    const edges = store().edges
    expect(store().updateParam('router', 'threshold', 0.9)).toEqual([])
    expect(store().edges).toEqual(edges)
    expect(store().notice).toBeNull()
  })

  it('keeps an edge from a port that was already missing', () => {
    store().setGraph({
      ...defaultGraphFixture,
      edges: [...defaultGraphFixture.edges, { id: 'x', source: 'router', sourcePort: 'route.nope', target: 'llm', targetPort: 'text' }],
    })
    store().updateParam('router', 'allowed_intents', ['billing'])
    expect(store().edges.some((e) => e.id === 'x')).toBe(true)
  })

  it('applies React Flow position changes', () => {
    store().setGraph(defaultGraphFixture)
    store().onNodesChange([{ type: 'position', id: 'router', position: { x: 9, y: 9 } }])
    expect(store().toGraph().nodes.find((n) => n.id === 'router')!.position).toEqual({ x: 9, y: 9 })
  })
})
