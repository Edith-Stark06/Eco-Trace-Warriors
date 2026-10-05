import { Component, type ErrorInfo, type ReactNode } from 'react';
import { ServerError } from '@/components/common/ServerError';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * Top-level error boundary.
 *
 * Catches render-time errors in the tree and shows a recoverable fallback
 * instead of a blank screen (docs/engineering/07_FRONTEND.md → never a dead
 * end). Class component because React error boundaries require lifecycle.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // TODO: forward to a monitoring service when observability is set up.
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    if (this.props.fallback) {
      return this.props.fallback;
    }

    return <ServerError fullScreen onRetry={this.handleReset} />;
  }
}
