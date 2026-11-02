import type { NodeCategory } from '../types'

export const CATEGORY_LABELS: Record<NodeCategory, string> = {
  io: 'Customer',
  jev: 'Jev decision',
  llm: 'LLM generation',
  tool: 'Deterministic tool',
  human: 'Human',
}
