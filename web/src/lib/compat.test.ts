import { describe, expect, it } from 'vitest'
import fixture from '../../../shared/fixtures/port-compat-cases.json'
import type { PortType } from '../types'
import { typeCompat, type Compat } from './compat'

const cases = fixture.cases as { source: PortType; target: PortType; expected: Compat }[]

describe('typeCompat', () => {
  it('covers every pair of port types', () => {
    expect(cases).toHaveLength(64)
  })

  it.each(cases)('$source -> $target is $expected', ({ source, target, expected }) => {
    expect(typeCompat(source, target)).toBe(expected)
  })
})
