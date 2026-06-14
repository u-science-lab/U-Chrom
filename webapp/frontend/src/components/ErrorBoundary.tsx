import { Component, ErrorInfo, ReactNode } from 'react'
import { reportViewDiagnostic } from '../diagnostics'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  // When set, a caught render error is fed back to the backend as a
  // `view.diagnostic` for this view so the agent can SEE it (get_view_state).
  viewId?: string
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
    // Feed the failure back to the agent if this boundary guards a named view.
    if (this.props.viewId) {
      reportViewDiagnostic({
        view_id: this.props.viewId,
        level: 'error',
        source: 'react-error-boundary',
        message: error.message || String(error),
        detail: errorInfo?.componentStack ?? undefined,
      })
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="h-full flex flex-col items-center justify-center p-8 bg-red-50 text-center">
          <div className="max-w-md">
            <div className="text-red-600 text-lg font-semibold mb-2">
              Rendering Error
            </div>
            <div className="text-sm text-gray-600 mb-4">
              The visualization component failed to initialize. This is often caused by WebGL limitations in your browser environment.
            </div>
            {this.state.error && (
              <details className="text-left text-xs bg-white p-3 rounded border border-gray-200">
                <summary className="cursor-pointer font-medium text-gray-700 mb-2">
                  Error details
                </summary>
                <pre className="text-red-600 whitespace-pre-wrap break-words">
                  {this.state.error.toString()}
                </pre>
              </details>
            )}
            <button
              onClick={() => window.location.reload()}
              className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
            >
              Reload Page
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
