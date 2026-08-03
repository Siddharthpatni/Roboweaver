'use client';

import React from 'react';
import { AlertOctagon, RefreshCw } from 'lucide-react';

interface Props {
  /** Remounts the boundary's children when this changes (e.g. the active tab
   * id) -- switching away from a crashed view and back gives it a clean try
   * without carrying over the error state from a different view. */
  resetKey: string;
  children: React.ReactNode;
}

interface State {
  error: Error | null;
  attempt: number;
}

const MAX_AUTO_RETRIES = 3;
const BASE_BACKOFF_MS = 1000;

/**
 * Contains a render crash to whatever is inside this boundary instead of
 * unmounting the whole app -- without it, one bad API response shape in any
 * single tab would blank Sidebar/TopBar along with it, and the only recovery
 * a user has is a manual page reload.
 *
 * Mirrors the backend's self-healing supervisor (server.py's
 * run_dashboard_supervised): the first few crashes retry automatically with
 * exponential backoff, no click required. Unlike the backend, retries are
 * capped here -- an error that keeps recurring is far more likely to be a
 * genuine bug than a transient glitch, and silently re-rendering forever
 * would burn CPU with nothing to show for it. After the cap, it falls back to
 * a manual "Try again" affordance rather than retrying forever.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  private retryTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(props: Props) {
    super(props);
    this.state = { error: null, attempt: 0 };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught a render error:', error, info.componentStack);
    if (this.state.attempt < MAX_AUTO_RETRIES) {
      const delay = BASE_BACKOFF_MS * 2 ** this.state.attempt;
      this.retryTimer = setTimeout(() => {
        this.setState((s) => ({ error: null, attempt: s.attempt + 1 }));
      }, delay);
    }
  }

  componentDidUpdate(prevProps: Props) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null, attempt: 0 });
    }
  }

  componentWillUnmount() {
    if (this.retryTimer) clearTimeout(this.retryTimer);
  }

  private manualRetry = () => {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.setState({ error: null, attempt: 0 });
  };

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    const willAutoRetry = this.state.attempt < MAX_AUTO_RETRIES;

    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="app-card p-6 max-w-md w-full space-y-3 text-center">
          <AlertOctagon className="w-6 h-6 text-rose-400 mx-auto" />
          <h3 className="text-[14px] font-semibold text-slate-200">
            This view hit an unexpected error
          </h3>
          <p className="text-[12px] text-slate-500 leading-relaxed">
            {this.state.error.message || 'Unknown error'}
          </p>
          {willAutoRetry ? (
            <p className="text-[11.5px] text-cyan-400 flex items-center justify-center gap-1.5">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              Retrying automatically… (attempt {this.state.attempt + 1}/{MAX_AUTO_RETRIES})
            </p>
          ) : (
            <button
              onClick={this.manualRetry}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 btn-neon text-[12.5px] mx-auto"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Try again
            </button>
          )}
          <p className="text-[10.5px] text-slate-600">
            The rest of the dashboard is unaffected — this is contained to this view.
          </p>
        </div>
      </div>
    );
  }
}
