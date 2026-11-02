// Mirror of the ParamSpec.check methods in server/app/models/params.py: the inspector refuses what
// the server would reject. Returns an error message, or null when the value is valid.
import type { ParamSpec } from '../types'
import { branchLabel } from './graphMapping'

const isNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const isStringList = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === 'string')

// Option values whose plain-English form isn't just the words with a capital.
const OPTION_LABELS: Record<string, string> = {
  faq: 'FAQ',
  kb: 'Knowledge base',
  no_internal_urls: 'No internal URLs',
  pii_request: 'PII request',
  ssn: 'SSN',
}

/** How an enum option reads in the UI. The saved value doesn't change. */
export function optionLabel(value: string): string {
  return OPTION_LABELS[value] ?? branchLabel(value)
}

/**
 * True when a param offers no real choice, so the UI hides it (Inspector and help panel). Its value
 * stays in the graph and is still validated. A one-item multi_enum isn't fixed: it can be ticked or not.
 */
export function isFixedParam(spec: ParamSpec): boolean {
  switch (spec.kind) {
    case 'enum':
      return spec.options.length === 1
    case 'number':
    case 'int':
      return spec.min === spec.max
    default:
      return false
  }
}

/** True when the UI leaves a param out: the catalog marks it hidden, or it offers no real choice. */
export function isHiddenParam(spec: ParamSpec): boolean {
  return spec.hidden === true || isFixedParam(spec)
}

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
