// The default edge plus a validation badge: issues on this edge color it and show at its middle.
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from '@xyflow/react'
import { worstSeverity } from '../lib/issues'
import { useValidationStore } from '../store/validationStore'

export function PipelineEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, style, selected }: EdgeProps) {
  const issues = useValidationStore((s) => s.index.byEdge[id])
  const severity = worstSeverity(issues)
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition })

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={style}
        className={[severity && `pipeline-edge--${severity}`, selected && 'pipeline-edge--selected'].filter(Boolean).join(' ')}
      />
      {severity && issues && (
        <EdgeLabelRenderer>
          <div
            className={`issue-badge issue-badge--${severity} issue-badge--edge`}
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            title={issues.map((i) => i.message).join('\n')}
            role="img"
            aria-label={`${issues.length} ${severity === 'error' ? 'error' : 'warning'}${issues.length > 1 ? 's' : ''} on this connection`}
            data-edge-id={id}
          >
            {severity === 'error' ? '!' : '⚠'} {issues.length}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}
