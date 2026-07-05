import { Component, type ReactNode } from "react";

// Contains render errors (e.g. a chart/table receiving an unexpected shape from
// the model-driven response) so one bad widget degrades to a small notice
// instead of white-screening the whole app.
export class ErrorBoundary extends Component<{ children: ReactNode; fallback?: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.error("SEMA render error:", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="rounded-xl border border-line bg-surfaceAlt px-4 py-3 text-sm text-muted">
            This part of the answer couldn't be displayed.
          </div>
        )
      );
    }
    return this.props.children;
  }
}
