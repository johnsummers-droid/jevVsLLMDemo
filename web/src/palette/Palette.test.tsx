import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { catalogNodes } from '../test/fixtures'
import { Palette } from './Palette'

afterEach(cleanup)

describe('Palette', () => {
  it('renders one card per catalog node, grouped by category', () => {
    render(<Palette nodes={catalogNodes} onAdd={() => {}} />)
    for (const definition of catalogNodes) {
      expect(screen.getByRole('button', { name: new RegExp(`^${definition.title}`) })).toBeTruthy()
    }
    const headings = screen.getAllByRole('heading').map((h) => h.textContent)
    expect(headings).toEqual(['Input / output', 'Jev', 'LLM', 'Tools', 'Human'])
  })

  it('adds a node on click', () => {
    const onAdd = vi.fn()
    render(<Palette nodes={catalogNodes} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /^Knowledge lookup/ }))
    expect(onAdd).toHaveBeenCalledWith('knowledge_lookup')
  })

  it('puts the node type on a drag', () => {
    render(<Palette nodes={catalogNodes} onAdd={() => {}} />)
    const setData = vi.fn()
    fireEvent.dragStart(screen.getByRole('button', { name: /^Knowledge lookup/ }), { dataTransfer: { setData } })
    expect(setData).toHaveBeenCalledWith('application/x-pipeline-node', 'knowledge_lookup')
  })
})
