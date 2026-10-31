// TEMPORARY quick fix (2026-10-31): the ?ref drop-down; see lib/referenceGraphs.ts.
import { REFERENCE_GRAPHS, viewReference } from '../lib/referenceGraphs'
import { useGraphStore } from '../store/graphStore'

const USER = ''

export function ReferencePicker() {
  const reference = useGraphStore((s) => s.reference)
  return (
    <label className="reference-picker">
      Graph
      <select
        value={reference ?? USER}
        onChange={(e) => void viewReference(e.target.value === USER ? null : e.target.value)}
      >
        <option value={USER}>User defined</option>
        {Object.entries(REFERENCE_GRAPHS).map(([name, { label }]) => (
          <option key={name} value={name}>
            {label}
          </option>
        ))}
      </select>
    </label>
  )
}
