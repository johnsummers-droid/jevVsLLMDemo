import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { isHiddenParam } from '../lib/params'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { catalogByType, catalogNodes, defaultGraphFixture } from '../test/fixtures'
import { Inspector } from './Inspector'

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const initialGraphState = useGraphStore.getState()

beforeEach(() => {
  useCatalogStore.setState({ status: 'ready', nodes: catalogNodes, byType: catalogByType, error: null })
  useGraphStore.setState(initialGraphState, true)
})

afterEach(cleanup)

function select(id: string) {
  useGraphStore.setState({ nodes: useGraphStore.getState().nodes.map((n) => ({ ...n, selected: n.id === id })) })
}

describe('Inspector', () => {
  it('asks for a selection when nothing is selected', () => {
    useGraphStore.getState().setGraph(defaultGraphFixture)
    render(<Inspector />)
    expect(screen.getByText(/Select a node/)).toBeTruthy()
  })

  it.each(catalogNodes.map((d) => d.type))('shows a field for every param of %s', (nodeType) => {
    const id = useGraphStore.getState().addNode(nodeType, { x: 0, y: 0 })
    select(id)
    render(<Inspector />)
    const definition = catalogByType[nodeType]
    expect(screen.getByRole('heading', { name: definition.title })).toBeTruthy()
    for (const spec of definition.params.filter((s) => !isHiddenParam(s))) {
      const field = spec.kind === 'multi_enum' ? screen.getByRole('group', { name: spec.label }) : screen.getByLabelText(new RegExp(`^${escape(spec.label)}`))
      expect(field, spec.key).toBeTruthy()
    }
    expect(screen.getByText('Cost per call')).toBeTruthy()
  })

  it('lists expanded branch ports with their own descriptions, and no technical labels', () => {
    useGraphStore.getState().setGraph(defaultGraphFixture)
    select('router')
    render(<Inspector />)
    expect(screen.getByText('Carries feature request messages.')).toBeTruthy()
    expect(screen.queryByText(/accepts several|^branch$/)).toBeNull()
  })

  it('edits a param in the store', () => {
    useGraphStore.getState().setGraph(defaultGraphFixture)
    select('router')
    render(<Inspector />)
    fireEvent.change(screen.getByRole('spinbutton', { name: /threshold/i }), { target: { value: '0.8' } })
    expect(useGraphStore.getState().toGraph().nodes.find((n) => n.id === 'router')!.params!.threshold).toBe(0.8)
  })

  it('re-expands branch ports and drops edges to removed branches', () => {
    useGraphStore.getState().setGraph(defaultGraphFixture)
    select('router')
    render(<Inspector />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Billing' }))
    expect(screen.queryByText('Carries billing messages.')).toBeNull()
    expect(useGraphStore.getState().edges.some((e) => e.sourceHandle === 'route.billing')).toBe(false)
    expect(useGraphStore.getState().notice).toMatch(/route\.billing → llm/)
  })

  it('shows its sections in order, each in its own bordered section', () => {
    const id = useGraphStore.getState().addNode('human_review_queue', { x: 0, y: 0 })
    select(id)
    render(<Inspector />)
    const headings = screen.getAllByRole('heading', { level: 3 })
    expect(headings.map((h) => h.textContent)).toEqual(['Parameters', 'Inputs', 'Outputs', 'Notes', 'Cost and latency assumptions'])
    for (const heading of headings) expect(heading.parentElement!.className).toBe('inspector__section')
    expect(screen.getByText('Each output can feed up to 4 connections.').parentElement).toBe(headings[3].parentElement)
  })

  it('hides params, drops the section when none are left, and keeps their values in the graph', () => {
    const id = useGraphStore.getState().addNode('customer_message', { x: 0, y: 0 })
    select(id)
    render(<Inspector />)
    expect(screen.queryByRole('heading', { name: 'Parameters' })).toBeNull()
    expect(screen.queryByLabelText(/^Language/)).toBeNull()
    expect(screen.queryByLabelText(/^Traffic mix/)).toBeNull()
    const params = useGraphStore.getState().nodes.find((n) => n.id === id)?.data.params
    expect(params?.language).toBe('en')
    expect(params?.traffic_mix).toBe('realistic')
  })

  it('shows only Review time on human review', () => {
    const id = useGraphStore.getState().addNode('human_review_queue', { x: 0, y: 0 })
    select(id)
    render(<Inspector />)
    expect(screen.queryByLabelText(/^Reviewers/)).toBeNull()
    expect(screen.getByLabelText(/^Review time/)).toBeTruthy()
  })

  it('has no notes about outputs on a node without outputs', () => {
    useGraphStore.getState().addNode('customer_response', { x: 0, y: 0 })
    select('customer_response')
    render(<Inspector />)
    expect(screen.queryByRole('heading', { name: 'Notes' })).toBeNull()
    expect(screen.queryByText(/Each output can feed/)).toBeNull()
  })

  it.each(catalogNodes.map((d) => d.type))('describes every shown port of %s', (nodeType) => {
    select(useGraphStore.getState().addNode(nodeType, { x: 0, y: 0 }))
    render(<Inspector />)
    const items = document.querySelectorAll('.inspector__port')
    expect(items.length).toBeGreaterThan(0)
    for (const item of items) expect(item.querySelector('.inspector__port-text')!.textContent).not.toBe('')
  })

  it('hides unused outputs, unless a graph connects one', () => {
    useGraphStore.getState().setGraph(defaultGraphFixture)
    select('router')
    render(<Inspector />)
    expect(screen.queryByText('Confidence')).toBeNull()
    expect(screen.getByText('Low confidence')).toBeTruthy()
    cleanup()
    act(() => {
      useGraphStore.setState({
        edges: [...useGraphStore.getState().edges, { id: 'x', source: 'router', sourceHandle: 'confidence', target: 'llm', targetHandle: 'context' }],
      })
    })
    render(<Inspector />)
    expect(screen.getByText('Confidence')).toBeTruthy()
  })

  it('deletes the node', () => {
    useGraphStore.getState().setGraph(defaultGraphFixture)
    select('llm')
    render(<Inspector />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete node' }))
    expect(useGraphStore.getState().nodes.some((n) => n.id === 'llm')).toBe(false)
  })
})
