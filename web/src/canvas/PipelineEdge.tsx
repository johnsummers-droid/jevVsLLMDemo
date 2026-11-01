// The default edge plus a validation badge (issues on this edge color it and show at its middle)
// and, during a run, the request dots the pulse animator moves along it (T23).
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from '@xyflow/react'
import { useEffect, useRef } from 'react'
import { worstSeverity } from '../lib/issues'
import { useGraphStore } from '../store/graphStore'
import { useRunStore } from '../store/runStore'
import { useValidationStore } from '../store/validationStore'
import { animator } from './pulses'

export function PipelineEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, style, selected }: EdgeProps) {
  const issues = useValidationStore((s) => s.index.byEdge[id])
  const viewingReference = useGraphStore((s) => s.reference !== null)
  const runTransfers = useRunStore((s) => s.edgeCounts[id] ?? 0)
  const transfers = viewingReference ? 0 : runTransfers
  const severity = worstSeverity(issues)
  const [path, labelX, labelY] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: 12 })
  const trackRef = useRef<SVGPathElement>(null)
  const layerRef = useRef<SVGGElement>(null)

  useEffect(() => {
    if (!trackRef.current || !layerRef.current) return
    return animator.track(id, trackRef.current, layerRef.current)
  }, [id, path])

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={style}
        className={[
          severity && `pipeline-edge--${severity}`,
          selected && 'pipeline-edge--selected',
          !severity && transfers > 0 && 'pipeline-edge--active', // issue colors stay visible
        ]
          .filter(Boolean)
          .join(' ')}
      />
      <path ref={trackRef} d={path} className="pulse-track" />
      <g ref={layerRef} className="pulse-layer" data-edge-id={id} data-transfers={transfers} />
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
