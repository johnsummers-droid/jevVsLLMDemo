// Server validation issues as a list. Clicking an issue about a node or edge selects that node.
import { useGraphStore } from '../store/graphStore'
import type { ValidationIssue } from '../types'

interface IssueListProps {
  issues: ValidationIssue[]
  /** Shown when there are no issues. */
  emptyText?: string
}

export function IssueList({ issues, emptyText = 'No issues.' }: IssueListProps) {
  const edges = useGraphStore((s) => s.edges)
  const nodes = useGraphStore((s) => s.nodes)
  const onNodesChange = useGraphStore((s) => s.onNodesChange)

  const nodeFor = (issue: ValidationIssue) =>
    issue.nodeId ?? edges.find((e) => e.id === issue.edgeId)?.source ?? null

  const select = (nodeId: string) =>
    onNodesChange(nodes.map((n) => ({ type: 'select' as const, id: n.id, selected: n.id === nodeId })))

  if (issues.length === 0) return <p className="issue-list__empty">{emptyText}</p>
  return (
    <ul className="issue-list">
      {issues.map((issue, i) => {
        const nodeId = nodeFor(issue)
        const where = issue.edgeId ? `connection ${issue.edgeId}` : [issue.nodeId, issue.portId].filter(Boolean).join(' · ')
        const body = (
          <>
            <span className={`issue-badge issue-badge--${issue.severity}`}>{issue.severity === 'error' ? 'Error' : 'Warning'}</span>
            <span className="issue-list__message">{issue.message}</span>
            {where && <span className="issue-list__where">{where}</span>}
            <code className="issue-list__code">{issue.code}</code>
          </>
        )
        return (
          <li key={`${issue.code}:${issue.nodeId}:${issue.edgeId}:${issue.portId}:${i}`} className="issue-list__item">
            {nodeId && nodes.some((n) => n.id === nodeId) ? (
              <button type="button" className="issue-list__button" onClick={() => select(nodeId)}>
                {body}
              </button>
            ) : (
              <div className="issue-list__button">{body}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
