// One React Flow node component per catalog category; nodeTypes.ts registers them.
import type { NodeProps } from '@xyflow/react'
import type { FlowNode } from '../types'
import { BaseNode } from './BaseNode'

export function IoNode(props: NodeProps<FlowNode>) {
  return <BaseNode {...props} category="io" />
}

export function JevNode(props: NodeProps<FlowNode>) {
  return (
    <BaseNode {...props} category="jev">
      <span className="pipeline-node__hint">bounded, typed decision</span>
    </BaseNode>
  )
}

export function LlmNode(props: NodeProps<FlowNode>) {
  return (
    <BaseNode {...props} category="llm">
      <span className="pipeline-node__hint">generates text</span>
    </BaseNode>
  )
}

export function ToolNode(props: NodeProps<FlowNode>) {
  return (
    <BaseNode {...props} category="tool">
      <span className="pipeline-node__hint">deterministic</span>
    </BaseNode>
  )
}

export function HumanNode(props: NodeProps<FlowNode>) {
  return <BaseNode {...props} category="human" />
}

export function UnknownNode(props: NodeProps<FlowNode>) {
  return <BaseNode {...props} category="unknown" />
}
