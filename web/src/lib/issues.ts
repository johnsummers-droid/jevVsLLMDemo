// Where each server validation issue is shown: an issue with an edgeId badges that edge; otherwise
// one with a nodeId badges that node (and its port, if any); the rest are graph-wide.
import type { Severity, ValidationIssue, ValidationReport } from '../types'

export interface IssueIndex {
  byNode: Record<string, ValidationIssue[]>
  byEdge: Record<string, ValidationIssue[]>
  /** Key: `${nodeId}:${portId}`. These issues are also in byNode. */
  byPort: Record<string, ValidationIssue[]>
  graph: ValidationIssue[]
}

export const EMPTY_INDEX: IssueIndex = { byNode: {}, byEdge: {}, byPort: {}, graph: [] }

export const portKey = (nodeId: string, portId: string) => `${nodeId}:${portId}`

function push(map: Record<string, ValidationIssue[]>, key: string, issue: ValidationIssue) {
  if (!map[key]) map[key] = []
  map[key].push(issue)
}

export function indexIssues(report: ValidationReport | null): IssueIndex {
  if (!report) return EMPTY_INDEX
  const index: IssueIndex = { byNode: {}, byEdge: {}, byPort: {}, graph: [] }
  for (const issue of report.issues) {
    if (issue.edgeId) {
      push(index.byEdge, issue.edgeId, issue)
    } else if (issue.nodeId) {
      push(index.byNode, issue.nodeId, issue)
      if (issue.portId) push(index.byPort, portKey(issue.nodeId, issue.portId), issue)
    } else {
      index.graph.push(issue)
    }
  }
  return index
}

/** "error" if any issue is an error, "warning" if any is a warning, else null. */
export function worstSeverity(issues: ValidationIssue[] | undefined): Severity | null {
  if (!issues?.length) return null
  return issues.some((i) => i.severity === 'error') ? 'error' : 'warning'
}

export function countBySeverity(issues: ValidationIssue[]): Record<Severity, number> {
  return {
    error: issues.filter((i) => i.severity === 'error').length,
    warning: issues.filter((i) => i.severity === 'warning').length,
  }
}
