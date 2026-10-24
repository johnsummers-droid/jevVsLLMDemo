import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ParamSpec } from '../types'
import { ParamField } from './ParamField'

afterEach(cleanup)

function setup(spec: ParamSpec, value: unknown = spec.default) {
  const onChange = vi.fn()
  render(<ParamField spec={spec} value={value} onChange={onChange} />)
  return onChange
}

const alert = () => screen.queryByRole('alert')

describe('ParamField', () => {
  it('number: commits a value in range, refuses one outside it', () => {
    const onChange = setup({ kind: 'number', key: 'threshold', label: 'Threshold', default: 0.5, min: 0, max: 1 })
    const input = screen.getByRole('spinbutton', { name: /Threshold/ })
    fireEvent.change(input, { target: { value: '0.7' } })
    expect(onChange).toHaveBeenLastCalledWith(0.7)
    fireEvent.change(input, { target: { value: '1.5' } })
    expect(alert()?.textContent).toMatch(/between 0 and 1/)
    expect(onChange).toHaveBeenCalledTimes(1)
    expect((input as HTMLInputElement).value).toBe('1.5')
  })

  it('number: refuses an empty field', () => {
    const onChange = setup({ kind: 'number', key: 'n', label: 'N', default: 0.5, min: 0, max: 1 })
    fireEvent.change(screen.getByRole('spinbutton', { name: /N/ }), { target: { value: '' } })
    expect(alert()).not.toBeNull()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('int: refuses a fraction', () => {
    const onChange = setup({ kind: 'int', key: 'top_k', label: 'Top k', default: 3, min: 1, max: 10 })
    const input = screen.getByRole('spinbutton', { name: /Top k/ })
    fireEvent.change(input, { target: { value: '2.5' } })
    expect(alert()?.textContent).toMatch(/whole number/)
    fireEvent.change(input, { target: { value: '5' } })
    expect(onChange).toHaveBeenCalledExactlyOnceWith(5)
    expect(alert()).toBeNull()
  })

  it('enum: offers the options and commits the choice', () => {
    const onChange = setup({ kind: 'enum', key: 'model', label: 'Model', default: 'small', options: ['small', 'large'] })
    const select = screen.getByRole('combobox', { name: 'Model' })
    expect([...(select as HTMLSelectElement).options].map((o) => o.value)).toEqual(['small', 'large'])
    fireEvent.change(select, { target: { value: 'large' } })
    expect(onChange).toHaveBeenCalledWith('large')
  })

  it('multi_enum: keeps option order and refuses going below the minimum', () => {
    const spec: ParamSpec = { kind: 'multi_enum', key: 'i', label: 'Intents', default: ['b'], options: ['a', 'b', 'c'] }
    const onChange = setup(spec, ['b'])
    fireEvent.click(screen.getByRole('checkbox', { name: 'a' }))
    expect(onChange).toHaveBeenLastCalledWith(['a', 'b'])
    fireEvent.click(screen.getByRole('checkbox', { name: 'b' }))
    expect(alert()?.textContent).toMatch(/at least 1/)
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('string_list: one item per line, refuses an item that is too long', () => {
    const onChange = setup({ kind: 'string_list', key: 'p', label: 'Phrases', default: [], maxLen: 5 })
    const box = screen.getByRole('textbox', { name: 'Phrases' })
    fireEvent.change(box, { target: { value: 'abc\n\n  de  \n' } })
    expect(onChange).toHaveBeenLastCalledWith(['abc', 'de'])
    fireEvent.change(box, { target: { value: 'abcdef' } })
    expect(alert()?.textContent).toMatch(/at most 5 characters/)
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('text: refuses text over the limit', () => {
    const onChange = setup({ kind: 'text', key: 'prompt', label: 'Prompt', default: '', maxLen: 3 })
    const box = screen.getByRole('textbox', { name: 'Prompt' })
    fireEvent.change(box, { target: { value: 'hey' } })
    fireEvent.change(box, { target: { value: 'hello' } })
    expect(onChange).toHaveBeenCalledExactlyOnceWith('hey')
    expect(alert()?.textContent).toMatch(/At most 3/)
  })

  it('bool: toggles', () => {
    const onChange = setup({ kind: 'bool', key: 'on', label: 'Enabled', default: false })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Enabled' }))
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('shows the help text', () => {
    setup({ kind: 'bool', key: 'on', label: 'Enabled', default: false, help: 'Turns it on.' })
    expect(screen.getByText('Turns it on.')).toBeTruthy()
  })
})
