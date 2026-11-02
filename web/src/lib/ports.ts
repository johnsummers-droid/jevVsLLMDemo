// What the UI shows of a node's ports: which ones, and each port's description.
import type { NodeDefinition, Port } from '../types'
import { expandOutputs } from './graphMapping'

/** The outputs to show. A hidden one still shows if a graph connects it, so no edge is left dangling. */
export function visibleOutputs(definition: NodeDefinition, params?: Record<string, unknown>, connected: ReadonlySet<string> = new Set()): Port[] {
  return expandOutputs(definition, params).filter((port) => !port.hidden || connected.has(port.id))
}

/** The inputs to show, by the same rule as visibleOutputs. */
export function visibleInputs(definition: NodeDefinition, connected: ReadonlySet<string> = new Set()): Port[] {
  return definition.inputs.filter((port) => !port.hidden || connected.has(port.id))
}

/** A port's one-line description. A branch such as route.billing fills in its template's (route.*). */
export function portDescription(definition: NodeDefinition, port: Port, input = false): string | undefined {
  const texts = (input ? definition.help?.inputs : definition.help?.outputs) ?? {}
  if (texts[port.id]) return texts[port.id]
  const template = definition.outputs.find((p) => p.dynamicFromParam && port.id.startsWith(p.id.replace(/\*$/, '')))
  return template && texts[template.id]?.replace('{branch}', port.label.toLowerCase())
}
