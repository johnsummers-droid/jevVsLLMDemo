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
    expect(headings).toEqual(['Jev decision nodes', 'LLM generation nodes', 'Deterministic tools', 'Human review', 'Customer'])
  })

  it('collapses and reopens a section from its header', () => {
    render(<Palette nodes={catalogNodes} onAdd={() => {}} />)
    const header = screen.getByRole('button', { name: 'Deterministic tools' })
    expect(header.getAttribute('aria-expanded')).toBe('true')
    fireEvent.click(header)
    expect(header.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('button', { name: /^Knowledge lookup/ })).toBeNull()
    expect(screen.getByRole('button', { name: /^Jev intent router/ })).toBeTruthy()
    fireEvent.click(header)
    expect(screen.getByRole('button', { name: /^Knowledge lookup/ })).toBeTruthy()
  })

  it('gives every card its category logo', () => {
    const { container } = render(<Palette nodes={catalogNodes} onAdd={() => {}} />)
    const logo = (card: string) => container.querySelector(`.node-card--${card} .node-card__panel img`)?.getAttribute('src')
    expect(logo('jev')).toContain('jev')
    expect(logo('llm')).toContain('gemini')
    expect(logo('tool')).toContain('abacus')
    expect(logo('io')).toContain('customer')
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
