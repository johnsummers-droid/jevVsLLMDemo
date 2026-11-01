// The logo in a node's colour panel, shared by canvas nodes and palette cards: TypeSafe for Jev,
// Gemini for LLM, an abacus for deterministic tools, the two customer icons for the start and end.
import abacus from '../assets/abacus-white.png'
import customerMessage from '../assets/customer-message.png'
import customerResponse from '../assets/customer-response.png'
import gemini from '../assets/gemini.png'
import jev from '../assets/jev.png'
import type { NodeCategory } from '../types'

const IMAGES: Partial<Record<NodeCategory, string>> = { jev, llm: gemini, tool: abacus }

interface CategoryIconProps {
  category: NodeCategory | 'unknown'
  /** Tells the customer message and customer response icons apart. */
  nodeType?: string
  /** Leave empty where text next to the icon already names the category. */
  alt?: string
  className?: string
}

export function CategoryIcon({ category, nodeType, alt = '', className = 'category-icon' }: CategoryIconProps) {
  const src = category === 'io' ? (nodeType === 'customer_response' ? customerResponse : customerMessage) : category === 'unknown' ? undefined : IMAGES[category]
  if (src) return <img src={src} alt={alt} className={className} draggable={false} />
  if (category === 'unknown') return <span className={className}>?</span>
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" role={alt ? 'img' : undefined} aria-label={alt || undefined} aria-hidden={alt ? undefined : true}>
      <circle cx="12" cy="7" r="4.5" />
      <path d="M3 22c0-5 4-8.5 9-8.5s9 3.5 9 8.5H3Z" />
    </svg>
  )
}
