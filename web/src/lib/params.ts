// Mirror of the ParamSpec.check methods in server/app/models/params.py: the inspector refuses what
// the server would reject. Returns an error message, or null when the value is valid.
import type { ParamSpec } from '../types'

const isNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const isStringList = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === 'string')

export function checkParam(spec: ParamSpec, value: unknown): string | null {
  switch (spec.kind) {
    case 'number':
    case 'int':
      if (!isNumber(value)) return spec.kind === 'int' ? 'Enter a whole number.' : 'Enter a number.'
      if (spec.kind === 'int' && !Number.isInteger(value)) return 'Enter a whole number.'
      if (value < spec.min || value > spec.max) return `Must be between ${spec.min} and ${spec.max}.`
      return null
    case 'enum':
      return typeof value === 'string' && spec.options.includes(value) ? null : 'Choose one of the options.'
    case 'multi_enum': {
      if (!isStringList(value)) return 'Expected a list of options.'
      if (new Set(value).size !== value.length) return 'Each option can be selected once.'
      const unknown = value.filter((v) => !spec.options.includes(v))
      if (unknown.length) return `Unknown options: ${unknown.join(', ')}.`
      const min = spec.minSelected ?? 1
      if (value.length < min) return `Select at least ${min}.`
      return null
    }
    case 'string_list': {
      if (!isStringList(value)) return 'Expected a list of strings.'
      const maxItems = spec.maxItems ?? 20
      const maxLen = spec.maxLen ?? 60
      if (value.length > maxItems) return `At most ${maxItems} items.`
      if (value.some((v) => v.length > maxLen)) return `Each item can be at most ${maxLen} characters.`
      return null
    }
    case 'text': {
      if (typeof value !== 'string') return 'Expected text.'
      const maxLen = spec.maxLen ?? 500
      return value.length > maxLen ? `At most ${maxLen} characters.` : null
    }
    case 'bool':
      return typeof value === 'boolean' ? null : 'Expected on or off.'
  }
}
