// The logo in a node's colour bar or panel, shared by canvas nodes and palette cards: TypeSafe for Jev,
// Gemini for LLM, an abacus for deterministic tools, the two customer icons for the start and end,
// a person with a magnifying glass for human review.
import { useId } from 'react'
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

// The mask cuts a gap in the person around the magnifying glass, so the lens reads at small sizes on
// any background. The id is per instance: a mask in a hidden panel would break the others' reference.
function HumanReviewIcon({ alt, className }: { alt: string; className: string }) {
  const maskId = `human-icon-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" role={alt ? 'img' : undefined} aria-label={alt || undefined} aria-hidden={alt ? undefined : true}>
      <mask id={maskId}>
        <rect width="24" height="24" fill="white" />
        <circle cx="16.5" cy="15.5" r="6.5" fill="black" />
        <path d="m19.5 18.5 4 4" stroke="black" strokeWidth="5" />
      </mask>
      <g mask={`url(#${maskId})`}>
        <circle cx="10" cy="6.5" r="4.5" />
        <path d="M1 22c0-5 4-8.5 9-8.5s9 3.5 9 8.5H1Z" />
      </g>
      <circle cx="16.5" cy="15.5" r="4" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="m19.6 18.6 3.4 3.4" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

export function CategoryIcon({ category, nodeType, alt = '', className = 'category-icon' }: CategoryIconProps) {
  const src = category === 'io' ? (nodeType === 'customer_response' ? customerResponse : customerMessage) : category === 'unknown' ? undefined : IMAGES[category]
  if (src) return <img src={src} alt={alt} className={className} draggable={false} />
  if (category === 'unknown') return <span className={className}>?</span>
  return <HumanReviewIcon alt={alt} className={className} />
}
