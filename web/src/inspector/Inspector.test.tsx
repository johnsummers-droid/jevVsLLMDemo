import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
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
    for (const spec of definition.params) {
      const field = spec.kind === 'multi_enum' ? screen.getByRole('group', { name: spec.label }) : screen.getByLabelText(new RegExp(`^${escape(spec.label)}`))
      expect(field, spec.key).toBeTruthy()
    }
    expect(screen.getByText('Cost per call')).toBeTruthy()
  })

  it('lists expanded branch ports and previews json payloads', () => {
    useGraphStore.getState().setGraph(defaultGraphFixture)
    select('router')
    render(<Inspector />)
    expect(screen.getByText('Feature request')).toBeTruthy()
    expect(within(screen.getByRole('list', { name: 'Distribution fields' })).getByText('probs')).toBeTruthy()
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
    fireEvent.click(screen.getByRole('checkbox', { name: 'billing' }))
    expect(screen.queryByText('Billing')).toBeNull()
    expect(useGraphStore.getState().edges.some((e) => e.sourceHandle === 'route.billing')).toBe(false)
    expect(useGraphStore.getState().notice).toMatch(/route\.billing → llm/)
  })

  it('deletes the node', () => {
    useGraphStore.getState().setGraph(defaultGraphFixture)
    select('llm')
    render(<Inspector />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete node' }))
    expect(useGraphStore.getState().nodes.some((n) => n.id === 'llm')).toBe(false)
  })
})
