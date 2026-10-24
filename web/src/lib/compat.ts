// Mirror of server/app/catalog/compat.py's type_compat. Both are tested against
// shared/fixtures/port-compat-cases.json; change them together.
import type { PortType } from '../types'

export type Compat = 'ok' | 'warn' | 'blocked'

/** Type-level check used for instant feedback while connecting. "warn" is allowed but flagged. */
export function typeCompat(source: PortType, target: PortType): Compat {
  if (source === target || target === 'any') return 'ok'
  if (source === 'any') return 'warn'
  return 'blocked'
}
