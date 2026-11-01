// The Pipeline Simulator logo (hexagon and name). The alt text carries the name for a heading.
import logo from '../assets/logo.png'

export function Logo({ className }: { className?: string }) {
  return <img src={logo} alt="Pipeline Simulator" className={['logo', className].filter(Boolean).join(' ')} />
}
