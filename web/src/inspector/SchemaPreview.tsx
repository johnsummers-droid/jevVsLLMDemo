// The fields of a json port's payload (Port.jsonSchemaRef), from shared/schema/payloads.schema.json.
import { schemaFields } from '../lib/schemaFields'

export function SchemaPreview({ name }: { name: string }) {
  const fields = schemaFields(name)
  if (fields.length === 0) return null
  return (
    <ul className="schema-preview" aria-label={`${name} fields`}>
      {fields.map((field) => (
        <li key={field.path} style={{ paddingLeft: `${field.depth * 12}px` }}>
          <code>{field.path.split('.').pop()}</code>
          {!field.required && <span className="schema-preview__optional">?</span>}
          <span className="schema-preview__type">{field.type}</span>
        </li>
      ))}
    </ul>
  )
}
