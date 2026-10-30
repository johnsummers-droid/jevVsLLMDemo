import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { useCatalogStore } from '../store/catalogStore'
import { useGraphStore } from '../store/graphStore'
import { catalogByType, catalogNodes, defaultGraphFixture } from '../test/fixtures'
import type { ValidationIssue } from '../types'
import { IssueList } from './IssueList'

const initialGraph = useGraphStore.getState()

beforeEach(() => {
  useCatalogStore.setState({ status: 'ready', nodes: catalogNodes, byType: catalogByType, error: null })
  useGraphStore.setState(initialGraph, true)
  useGraphStore.getState().setGraph(defaultGraphFixture)
})

afterEach(cleanup)

const issues: ValidationIssue[] = [
  { code: 'UNCONNECTED_BRANCH', severity: 'warning', message: 'Branch dropped.', nodeId: 'policy', edgeId: null, portId: 'route.block' },
  { code: 'CYCLE', severity: 'error', message: 'Loop.', nodeId: null, edgeId: 'llm.text->policy.text', portId: null },
  { code: 'NO_HUMAN_FALLBACK', severity: 'warning', message: 'No fallback.', nodeId: null, edgeId: null, portId: null },
]

const selectedIds = () => useGraphStore.getState().nodes.filter((n) => n.selected).map((n) => n.id)

describe('IssueList', () => {
  it('shows every issue with its severity, message and code', () => {
    render(<IssueList issues={issues} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByText('Loop.')).toBeTruthy()
    expect(screen.getByText('Error')).toBeTruthy()
    expect(screen.getAllByText('Warning')).toHaveLength(2)
    expect(screen.getByText('NO_HUMAN_FALLBACK')).toBeTruthy()
  })

  it('selects the node an issue is about, or the source of its edge', () => {
    render(<IssueList issues={issues} />)
    fireEvent.click(screen.getByRole('button', { name: /Branch dropped/ }))
    expect(selectedIds()).toEqual(['policy'])
    fireEvent.click(screen.getByRole('button', { name: /Loop/ }))
    expect(selectedIds()).toEqual(['llm'])
  })

  it('does not make graph-wide issues clickable', () => {
    render(<IssueList issues={issues} />)
    expect(screen.queryByRole('button', { name: /No fallback/ })).toBeNull()
  })

  it('shows the empty text', () => {
    render(<IssueList issues={[]} emptyText="All good." />)
    expect(screen.getByText('All good.')).toBeTruthy()
  })
})
