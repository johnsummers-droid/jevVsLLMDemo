import { describe, expect, it } from 'vitest'
import type { ValidationIssue } from '../types'
import { countBySeverity, indexIssues, worstSeverity } from './issues'

const issue = (over: Partial<ValidationIssue>): ValidationIssue => ({
  code: 'CYCLE',
  severity: 'error',
  message: 'm',
  nodeId: null,
  edgeId: null,
  portId: null,
  ...over,
})

describe('indexIssues', () => {
  it('puts each issue on its edge, else its node (and port), else the graph', () => {
    const onEdge = issue({ code: 'INCOMPATIBLE_PORTS', nodeId: 'llm', edgeId: 'e1', portId: 'text' })
    const onPort = issue({ code: 'UNCONNECTED_BRANCH', severity: 'warning', nodeId: 'router', portId: 'route.x' })
    const onNode = issue({ code: 'INVALID_PARAM', nodeId: 'router' })
    const global = issue({ code: 'NO_SINK' })
    const index = indexIssues({ ok: false, issues: [onEdge, onPort, onNode, global] })
    expect(index.byEdge).toEqual({ e1: [onEdge] })
    expect(index.byNode).toEqual({ router: [onPort, onNode] })
    expect(index.byPort).toEqual({ 'router:route.x': [onPort] })
    expect(index.graph).toEqual([global])
  })

  it('is empty without a report', () => {
    expect(indexIssues(null)).toEqual({ byNode: {}, byEdge: {}, byPort: {}, graph: [] })
  })
})

describe('severity helpers', () => {
  it('picks the worst severity', () => {
    expect(worstSeverity(undefined)).toBeNull()
    expect(worstSeverity([issue({ severity: 'warning' })])).toBe('warning')
    expect(worstSeverity([issue({ severity: 'warning' }), issue({ severity: 'error' })])).toBe('error')
  })

  it('counts by severity', () => {
    expect(countBySeverity([issue({}), issue({ severity: 'warning' }), issue({ severity: 'warning' })])).toEqual({
      error: 1,
      warning: 2,
    })
  })
})
