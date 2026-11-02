import { describe, expect, it } from 'vitest'
import { catalogByType } from '../test/fixtures'
import { portDescription, visibleInputs, visibleOutputs } from './ports'

const router = catalogByType.jev_intent_router

describe('visibleOutputs', () => {
  it('leaves out hidden outputs', () => {
    expect(visibleOutputs(router).map((p) => p.id)).toEqual([
      'route.billing',
      'route.technical_support',
      'route.bug_report',
      'route.feature_request',
      'route.low_confidence',
    ])
    expect(visibleOutputs(catalogByType.customer_message).map((p) => p.id)).toEqual(['text'])
  })

  it('keeps a hidden output that a graph connects', () => {
    expect(visibleOutputs(router, undefined, new Set(['confidence'])).map((p) => p.id)).toContain('confidence')
  })
})

describe('visibleInputs', () => {
  const human = catalogByType.human_review_queue
  it('leaves out hidden inputs unless a graph connects one', () => {
    expect(visibleInputs(human).map((p) => p.id)).toEqual(['text'])
    expect(visibleInputs(catalogByType.policy_engine).map((p) => p.id)).toEqual(['text'])
    expect(visibleInputs(human, new Set(['context'])).map((p) => p.id)).toEqual(['text', 'context'])
    expect(visibleInputs(catalogByType.llm_answer_generator).map((p) => p.id)).toEqual(['text', 'context'])
  })
})

describe('portDescription', () => {
  it('finds exact ports and falls back to a branch template', () => {
    const [billing] = visibleOutputs(router)
    expect(portDescription(router, billing)).toBe('Carries billing messages.')
    const low = visibleOutputs(router).find((p) => p.id === 'route.low_confidence')!
    expect(portDescription(router, low)).toBe(router.help!.outputs!['route.low_confidence'])
    expect(portDescription(router, router.inputs[0], true)).toBe(router.help!.inputs!.text)
  })
})
