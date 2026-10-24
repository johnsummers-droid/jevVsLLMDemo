// A port handle whose color and shape show its PortType (see .typed-handle--<type> in App.css).
import { Handle, Position } from '@xyflow/react'
import type { Port } from '../types'

interface TypedHandleProps {
  port: Port
  kind: 'source' | 'target'
}

export function TypedHandle({ port, kind }: TypedHandleProps) {
  return (
    <Handle
      id={port.id}
      type={kind}
      position={kind === 'source' ? Position.Right : Position.Left}
      className={`typed-handle typed-handle--${port.type}`}
      title={`${port.label} (${port.type})`}
    />
  )
}
