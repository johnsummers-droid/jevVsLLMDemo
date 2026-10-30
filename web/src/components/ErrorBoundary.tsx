// Contains a crash in one panel (T24): the rest of the page keeps working, and the panel offers a
// retry. Without it, one render error blanks the whole page (as a metrics-bar bug once did).
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  /** What the panel is, for the message: "the run bar". */
  name: string
  children: ReactNode
}

export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Error in ${this.props.name}:`, error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="panel-error" role="alert">
        Something went wrong in {this.props.name}.{' '}
        <button type="button" className="button button--small" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    )
  }
}
