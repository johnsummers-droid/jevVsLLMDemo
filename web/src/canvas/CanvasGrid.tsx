// The faint grid behind both canvases (the team's and the read-only reference view).
import { Background, BackgroundVariant } from '@xyflow/react'

export function CanvasGrid() {
  return <Background variant={BackgroundVariant.Lines} gap={32} color="rgb(255 255 255 / 0.05)" />
}
