// One editor per ParamSpec kind. Invalid input stays in the field with an error and is not
// committed; checkParam mirrors the server's rules.
import { useId, useState, type ReactNode } from 'react'
import { checkParam } from '../lib/params'
import type { ParamSpec } from '../types'

interface ParamFieldProps {
  spec: ParamSpec
  value: unknown
  onChange: (value: unknown) => void
}

const toText = (value: unknown) => (value === undefined || value === null ? '' : String(value))
const toLines = (value: unknown) => (Array.isArray(value) ? value.join('\n') : '')
const parseNumber = (text: string) => (text.trim() === '' ? NaN : Number(text))
const parseLines = (text: string) => text.split('\n').map((line) => line.trim()).filter(Boolean)

export function ParamField({ spec, value, onChange }: ParamFieldProps) {
  const id = useId()
  const [draft, setDraft] = useState(() => (spec.kind === 'string_list' ? toLines(value) : toText(value)))
  const [error, setError] = useState<string | null>(null)

  const commit = (next: unknown) => {
    const problem = checkParam(spec, next)
    setError(problem)
    if (!problem) onChange(next)
  }

  const editText = (text: string, parse: (text: string) => unknown) => {
    setDraft(text)
    commit(parse(text))
  }

  let control: ReactNode
  switch (spec.kind) {
    case 'number':
      control = (
        <div className="param-field__number">
          <input
            type="range"
            aria-hidden="true"
            tabIndex={-1}
            min={spec.min}
            max={spec.max}
            step={spec.step ?? 0.05}
            value={Number.isFinite(parseNumber(draft)) ? draft : spec.default}
            onChange={(e) => editText(e.target.value, parseNumber)}
          />
          <input id={id} type="number" step={spec.step ?? 0.05} value={draft} onChange={(e) => editText(e.target.value, parseNumber)} />
        </div>
      )
      break
    case 'int':
      control = <input id={id} type="number" step={1} value={draft} onChange={(e) => editText(e.target.value, parseNumber)} />
      break
    case 'enum':
      control = (
        <select id={id} value={toText(value)} onChange={(e) => commit(e.target.value)}>
          {spec.options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      )
      break
    case 'multi_enum': {
      const selected = Array.isArray(value) ? (value as string[]) : []
      const toggle = (option: string) => {
        const next = selected.includes(option) ? selected.filter((v) => v !== option) : [...selected, option]
        commit(spec.options.filter((o) => next.includes(o)))
      }
      control = (
        <div id={id} role="group" aria-label={spec.label} className="param-field__options">
          {spec.options.map((option) => (
            <label key={option} className="param-field__option">
              <input type="checkbox" checked={selected.includes(option)} onChange={() => toggle(option)} />
              {option}
            </label>
          ))}
        </div>
      )
      break
    }
    case 'string_list':
      control = (
        <textarea id={id} rows={4} value={draft} placeholder="One per line" onChange={(e) => editText(e.target.value, parseLines)} />
      )
      break
    case 'text':
      control = <textarea id={id} rows={4} value={draft} onChange={(e) => editText(e.target.value, (t) => t)} />
      break
    case 'bool':
      control = <input id={id} type="checkbox" checked={value === true} onChange={(e) => commit(e.target.checked)} />
      break
  }

  return (
    <div className={`param-field param-field--${spec.kind}`}>
      <label className="param-field__label" htmlFor={spec.kind === 'multi_enum' ? undefined : id}>
        {spec.label}
        {(spec.kind === 'number' || spec.kind === 'int') && (
          <span className="param-field__range">
            {spec.min}–{spec.max}
          </span>
        )}
      </label>
      {control}
      {spec.help && <p className="param-field__help">{spec.help}</p>}
      {error && (
        <p className="param-field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
