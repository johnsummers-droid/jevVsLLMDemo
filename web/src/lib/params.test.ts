import { describe, expect, it } from 'vitest'
import type { ParamSpec } from '../types'
import { checkParam } from './params'

const number: ParamSpec = { kind: 'number', key: 'n', label: 'N', default: 0.5, min: 0, max: 1 }
const int: ParamSpec = { kind: 'int', key: 'i', label: 'I', default: 3, min: 1, max: 10 }
const enumSpec: ParamSpec = { kind: 'enum', key: 'e', label: 'E', default: 'a', options: ['a', 'b'] }
const multi: ParamSpec = { kind: 'multi_enum', key: 'm', label: 'M', default: ['a'], options: ['a', 'b', 'c'] }
const multi2: ParamSpec = { ...multi, minSelected: 2 }
const list: ParamSpec = { kind: 'string_list', key: 's', label: 'S', default: [], maxItems: 2, maxLen: 5 }
const text: ParamSpec = { kind: 'text', key: 't', label: 'T', default: '', maxLen: 4 }
const bool: ParamSpec = { kind: 'bool', key: 'b', label: 'B', default: false }

const cases: [string, ParamSpec, unknown, boolean][] = [
  ['number in range', number, 0.25, true],
  ['number at bound', number, 1, true],
  ['number above max', number, 1.01, false],
  ['number as string', number, '0.5', false],
  ['number NaN', number, NaN, false],
  ['int', int, 4, true],
  ['int fraction', int, 4.5, false],
  ['int below min', int, 0, false],
  ['enum option', enumSpec, 'b', true],
  ['enum unknown', enumSpec, 'z', false],
  ['multi subset', multi, ['a', 'c'], true],
  ['multi empty', multi, [], false],
  ['multi below minSelected', multi2, ['a'], false],
  ['multi duplicate', multi, ['a', 'a'], false],
  ['multi unknown', multi, ['a', 'z'], false],
  ['list ok', list, ['ab', 'cde'], true],
  ['list empty', list, [], true],
  ['list too many', list, ['a', 'b', 'c'], false],
  ['list item too long', list, ['abcdef'], false],
  ['list not strings', list, [1], false],
  ['text ok', text, 'abcd', true],
  ['text too long', text, 'abcde', false],
  ['bool', bool, true, true],
  ['bool as string', bool, 'true', false],
]

describe('checkParam', () => {
  it.each(cases)('%s', (_name, spec, value, valid) => {
    const error = checkParam(spec, value)
    if (valid) expect(error).toBeNull()
    else expect(error).toEqual(expect.any(String))
  })

  it('applies the server defaults for optional limits', () => {
    const bare: ParamSpec = { kind: 'string_list', key: 's', label: 'S', default: [] }
    expect(checkParam(bare, Array(20).fill('x'))).toBeNull()
    expect(checkParam(bare, Array(21).fill('x'))).not.toBeNull()
    expect(checkParam(bare, ['x'.repeat(61)])).not.toBeNull()
  })
})
