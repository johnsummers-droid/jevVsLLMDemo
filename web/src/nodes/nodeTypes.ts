import type { NodeTypes } from '@xyflow/react'
import { HumanNode, IoNode, JevNode, LlmNode, ToolNode, UnknownNode } from './CategoryNodes'

/** React Flow node type (the catalog category, see graphMapping.flowNodeType) -> component. */
export const nodeTypes: NodeTypes = {
  io: IoNode,
  jev: JevNode,
  llm: LlmNode,
  tool: ToolNode,
  human: HumanNode,
  unknown: UnknownNode,
}
