// Validation issues land on the right node, port and edge.
import { cleanup, render, screen } from '@testing-library/react'
import { Position, ReactFlowProvider, type EdgeProps, type NodeProps } from '@xyflow/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { indexIssues } from '../lib/issues'
import { JevNode } from '../nodes/CategoryNodes'
import { useCatalogStore } from '../store/catalogStore'
import { useValidationStore } from '../store/validationStore'
import { catalogByType, catalogNodes } from '../test/fixtures'
import type { FlowNode, ValidationReport } from '../types'
import { PipelineEdge } from './PipelineEdge'

const report: ValidationReport = {
  ok: false,
  issues: [
    { code: 'UNCONNECTED_BRANCH', severity: 'warning', message: 'Branch dropped.', nodeId: 'router', edgeId: null, portId: 'route.low_confidence' },
    { code: 'INVALID_PARAM', severity: 'error', message: 'Bad threshold.', nodeId: 'router', edgeId: null, portId: null },
    { code: 'CYCLE', severity: 'error', message: 'Loop.', nodeId: 'router', edgeId: 'e-bad', portId: null },
    { code: 'ANY_SOURCE', severity: 'warning', message: 'Any source.', nodeId: 'llm', edgeId: 'e-warn', portId: 'text' },
  ],
}

beforeEach(() => {
  useCatalogStore.setState({ status: 'ready', nodes: catalogNodes, byType: catalogByType, error: null })
  useValidationStore.setState({ status: 'done', report, index: indexIssues(report), error: null })
})

afterEach(cleanup)

function renderRouter(id = 'router') {
  const props = {
    id,
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
  return render(
    <ReactFlowProvider>
      <JevNode {...props} />
    </ReactFlowProvider>,
  )
}

function renderEdge(id: string) {
  const props = {
    id,
    source: 'a',
    target: 'b',
    sourceX: 0,
    sourceY: 0,
    targetX: 100,
    targetY: 0,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  } as EdgeProps
  return render(
    <ReactFlowProvider>
      <svg>
        <PipelineEdge {...props} />
      </svg>
    </ReactFlowProvider>,
  )
}

describe('node badges', () => {
  it('shows the node issues (not its edge issues) with the worst severity', () => {
    const { container } = renderRouter()
    const badge = screen.getByRole('img', { name: '2 errors on this node' })
    expect(badge.getAttribute('title')).toBe('Branch dropped.\nBad threshold.')
    expect(container.querySelector('.pipeline-node')!.classList).toContain('pipeline-node--error')
  })

  it('marks the port the issue is about', () => {
    const { container } = renderRouter()
    const marked = [...container.querySelectorAll('.port--warning')].map((el) => el.textContent)
    expect(marked).toEqual(['Low confidencetext'])
    expect(container.querySelectorAll('.port--error')).toHaveLength(0)
  })

  it('shows nothing on a node without issues', () => {
    const { container } = renderRouter('other')
    expect(screen.queryByRole('img', { name: /on this (node|connection)/ })).toBeNull()
    expect(container.querySelector('.pipeline-node--error, .pipeline-node--warning')).toBeNull()
  })
})

describe('edge badges', () => {
  it.each([
    ['e-bad', 'pipeline-edge--error'],
    ['e-warn', 'pipeline-edge--warning'],
  ])('colors edge %s', (id, cls) => {
    const { container } = renderEdge(id)
    expect(container.querySelector('path.react-flow__edge-path')!.classList).toContain(cls)
  })

  it('leaves a clean edge alone', () => {
    const { container } = renderEdge('e-ok')
    const classes = [...container.querySelector('path.react-flow__edge-path')!.classList]
    expect(classes.some((c) => c.startsWith('pipeline-edge--'))).toBe(false)
  })
})
