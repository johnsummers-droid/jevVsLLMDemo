// Flattens a payload JSON Schema (shared/schema/payloads.schema.json) into rows for the
// inspector's schema preview: one row per field, nested objects indented.
import payloads from '../../../shared/schema/payloads.schema.json'

interface JsonSchema {
  type?: string
  $ref?: string
  items?: JsonSchema
  properties?: Record<string, JsonSchema>
  additionalProperties?: JsonSchema | boolean
  required?: string[]
}

export interface SchemaField {
  path: string
  type: string
  depth: number
  required: boolean
}

const DEFS = (payloads as { $defs: Record<string, JsonSchema> }).$defs
const MAX_DEPTH = 3

const refName = (ref: string) => ref.split('/').pop() ?? ref

function typeLabel(schema: JsonSchema): string {
  if (schema.$ref) return refName(schema.$ref)
  if (schema.type === 'array') return `${schema.items ? typeLabel(schema.items) : 'unknown'}[]`
  if (schema.type === 'object' && typeof schema.additionalProperties === 'object') {
    return `map of ${typeLabel(schema.additionalProperties)}`
  }
  return schema.type ?? 'unknown'
}

/** The object schema to expand under a field, if any (a $ref, or an array of $refs). */
function nestedRef(schema: JsonSchema): string | null {
  if (schema.$ref) return refName(schema.$ref)
  if (schema.type === 'array' && schema.items?.$ref) return refName(schema.items.$ref)
  return null
}

export function hasPayloadSchema(name: string): boolean {
  return name in DEFS
}

export function schemaFields(name: string, depth = 0, prefix = ''): SchemaField[] {
  const schema = DEFS[name]
  if (!schema?.properties || depth >= MAX_DEPTH) return []
  return Object.entries(schema.properties).flatMap(([key, field]) => {
    const path = prefix ? `${prefix}.${key}` : key
    const row: SchemaField = { path, type: typeLabel(field), depth, required: schema.required?.includes(key) ?? false }
    const nested = nestedRef(field)
    return [row, ...(nested ? schemaFields(nested, depth + 1, field.type === 'array' ? `${path}[]` : path) : [])]
  })
}
