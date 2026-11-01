// The drop-down for viewing a reference graph on the team canvas: with ?ref (bundled graphs), or
// after the official run (graphs from the server, T40).
import { useGraphStore } from '../store/graphStore'
import type { ReferenceGraphInfo } from '../types'

const USER = ''

interface ReferencePickerProps {
  label: string
  graphs: ReferenceGraphInfo[]
  onPick: (name: string | null) => Promise<void>
}

export function ReferencePicker({ label, graphs, onPick }: ReferencePickerProps) {
  const reference = useGraphStore((s) => s.reference)
  return (
    <label className="reference-picker">
      {label}
      <select
        value={reference ?? USER}
        onChange={(e) => void onPick(e.target.value === USER ? null : e.target.value)}
      >
        <option value={USER}>User defined</option>
        {graphs.map(({ name, label: optionLabel }) => (
          <option key={name} value={name}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  )
}
