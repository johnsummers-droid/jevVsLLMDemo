import { describe, expect, it } from 'vitest'
import { catalogNodes } from '../test/fixtures'
import { hasPayloadSchema, schemaFields } from './schemaFields'

describe('schemaFields', () => {
  it('knows every jsonSchemaRef used by the catalog', () => {
    const refs = catalogNodes
      .flatMap((n) => [...n.inputs, ...n.outputs])
      .flatMap((p) => (p.jsonSchemaRef ? [p.jsonSchemaRef] : []))
    expect(refs.length).toBeGreaterThan(0)
    for (const ref of refs) expect(hasPayloadSchema(ref), ref).toBe(true)
  })

  it('expands nested arrays of objects', () => {
    expect(schemaFields('Docs')).toEqual([
      { path: 'docs', type: 'Doc[]', depth: 0, required: false },
      { path: 'docs[].id', type: 'string', depth: 1, required: true },
      { path: 'docs[].title', type: 'string', depth: 1, required: true },
      { path: 'docs[].snippet', type: 'string', depth: 1, required: true },
      { path: 'docs[].intent', type: 'string', depth: 1, required: true },
      { path: 'docs[].score', type: 'integer', depth: 1, required: true },
    ])
  })

  it('describes maps', () => {
    expect(schemaFields('Distribution')).toEqual([{ path: 'probs', type: 'map of number', depth: 0, required: true }])
  })

  it('returns nothing for an unknown name', () => {
    expect(schemaFields('Nope')).toEqual([])
  })
})
