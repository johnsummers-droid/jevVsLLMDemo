// The "?" buttons (palette, canvas node, Inspector) and the help panel (plan1.txt S1-S8).
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { ReactFlowProvider, type NodeProps } from '@xyflow/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Inspector } from '../inspector/Inspector'
import { JevNode } from '../nodes/CategoryNodes'
import { Palette } from '../palette/Palette'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { useHelpStore } from '../store/helpStore'
import { catalogByType, catalogNodes } from '../test/fixtures'
import type { FlowNode } from '../types'
import { HelpPanel } from './HelpPanel'

const initialHelp = useHelpStore.getState()
const initialGraph = useGraphStore.getState()

beforeEach(() => {
  useCatalogStore.setState({ status: 'ready', nodes: catalogNodes, byType: catalogByType, error: null })
  useHelpStore.setState(initialHelp, true)
  useGraphStore.setState(initialGraph, true)
})

afterEach(cleanup)

const panel = () => screen.queryByRole('complementary', { name: /^Help:/ })

describe('help panel', () => {
  it.each(catalogNodes.map((d) => d.type))('renders every section of %s', (nodeType) => {
    const definition = catalogByType[nodeType]
    const help = definition.help!
    render(<HelpPanel />)
    act(() => useHelpStore.getState().open(nodeType))
    const region = within(screen.getByRole('complementary', { name: `Help: ${definition.title}` }))
    expect(region.getByRole('heading', { level: 2, name: definition.title })).toBeTruthy()
    const headings = region.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(headings).toEqual(
      [
        'What it is',
        'Where it goes',
        'How it works',
        help.example && 'Example',
        help.tips?.length && 'Tips',
        definition.inputs.length && 'Inputs',
        definition.params.length && 'Settings',
        definition.outputs.length && 'Outputs',
        'Cost and speed',
      ].filter(Boolean),
    )
    const text = document.getElementById('help-panel')!.textContent!
    for (const s of [help.summary, help.placement, ...help.howItWorks, ...(help.tips ?? [])]) expect(text).toContain(s)
    for (const spec of definition.params) {
      expect(text).toContain(spec.key)
      expect(text).toContain(help.params![spec.key])
    }
    for (const port of definition.outputs) expect(text).toContain(help.outputs![port.id])
    if (help.example) {
      expect(text).toContain(help.example.explanation)
      if (help.example.inputText) expect(text).toContain(help.example.inputText)
      if (help.example.firedBranch) expect(text).toContain(help.example.firedBranch)
    }
  })

  it('closes with x and with Esc, but not while typing', () => {
    render(
      <>
        <input aria-label="typing" />
        <HelpPanel />
      </>,
    )
    act(() => useHelpStore.getState().open('policy_engine'))
    fireEvent.keyDown(screen.getByLabelText('typing'), { key: 'Escape' })
    expect(panel()).not.toBeNull()
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(panel()).toBeNull()
    act(() => useHelpStore.getState().open('policy_engine'))
    fireEvent.click(screen.getByRole('button', { name: 'Close help' }))
    expect(panel()).toBeNull()
  })

  it('moves focus to its heading and resizes from the keyboard', () => {
    render(<HelpPanel />)
    act(() => useHelpStore.getState().open('policy_engine'))
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 2, name: 'Policy engine' }))
    const handle = screen.getByRole('separator', { name: 'Resize help panel' })
    fireEvent.keyDown(handle, { key: 'ArrowUp' })
    expect(useHelpStore.getState().height).toBeCloseTo(0.45)
    for (let i = 0; i < 20; i++) fireEvent.keyDown(handle, { key: 'ArrowUp' })
    expect(useHelpStore.getState().height).toBe(0.8)
  })

  it('renders nothing for a type without help', () => {
    render(<HelpPanel />)
    act(() => useHelpStore.getState().open('not_a_node'))
    expect(panel()).toBeNull()
  })
})

describe('"?" buttons', () => {
  it('the palette "?" opens help without adding the node, and stays enabled when read-only', () => {
    const onAdd = vi.fn()
    render(
      <>
        <Palette nodes={catalogNodes} onAdd={onAdd} disabled />
        <HelpPanel />
      </>,
    )
    const help = screen.getByRole('button', { name: 'Help: Knowledge lookup' }) as HTMLButtonElement
    expect(help.disabled).toBe(false)
    expect(help.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(help)
    expect(onAdd).not.toHaveBeenCalled()
    expect(panel()?.getAttribute('aria-label')).toBe('Help: Knowledge lookup')
    expect(help.getAttribute('aria-expanded')).toBe('true')
    expect(help.getAttribute('aria-controls')).toBe('help-panel')
    fireEvent.click(screen.getByRole('button', { name: 'Help: Policy engine' }))
    expect(panel()?.getAttribute('aria-label')).toBe('Help: Policy engine')
    expect(screen.getAllByRole('complementary', { name: /^Help:/ })).toHaveLength(1)
    // Closing returns focus to the "?" that opened it.
    const policy = screen.getByRole('button', { name: 'Help: Policy engine' })
    fireEvent.keyDown(document.body, { key: 'Escape' })
    expect(document.activeElement).toBe(policy)
  })

  it('the canvas "?" neither selects nor drags its node', () => {
    const props = {
      id: 'router',
      type: 'jev',
      data: { nodeType: 'jev_intent_router', params: {}, label: null },
      selected: false,
      dragging: false,
      isConnectable: true,
      zIndex: 0,
      positionAbsoluteX: 0,
      positionAbsoluteY: 0,
      draggable: true,
      selectable: true,
      deletable: true,
    } as NodeProps<FlowNode>
    const onNode = vi.fn()
    render(
      <ReactFlowProvider>
        {/* stands in for React Flow's node wrapper, which selects on click and drags on mousedown */}
        <div onClick={onNode} onMouseDown={onNode} onPointerDown={onNode} onKeyDown={onNode}>
          <JevNode {...props} />
        </div>
      </ReactFlowProvider>,
    )
    const help = screen.getByRole('button', { name: 'Help: Jev intent router' })
    expect(help.classList.contains('nodrag')).toBe(true)
    expect(help.classList.contains('nopan')).toBe(true)
    fireEvent.pointerDown(help)
    fireEvent.mouseDown(help)
    fireEvent.click(help)
    fireEvent.keyDown(help, { key: 'Enter' })
    expect(onNode).not.toHaveBeenCalled()
    expect(useHelpStore.getState().nodeType).toBe('jev_intent_router')
  })

  it('the Inspector header has a "?" for the selected node', () => {
    const id = useGraphStore.getState().addNode('policy_engine', { x: 0, y: 0 })
    useGraphStore.setState({ nodes: useGraphStore.getState().nodes.map((n) => ({ ...n, selected: n.id === id })) })
    useGraphStore.getState().setLocked(true)
    render(<Inspector />)
    const help = screen.getByRole('button', { name: 'Help: Policy engine' }) as HTMLButtonElement
    expect(help.disabled).toBe(false)
    fireEvent.click(help)
    expect(useHelpStore.getState().nodeType).toBe('policy_engine')
  })
})
