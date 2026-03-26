import React, { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * React Error Boundary — catches unhandled render errors so the
 * entire app never shows a white screen.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary] Uncaught render error:", error, info.componentStack);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            minHeight: "100vh",
            padding: "2rem",
            fontFamily: "system-ui, sans-serif",
            background: "#0f0f23",
            color: "#e2e8f0",
          }}
        >
          <div
            style={{
              maxWidth: 480,
              textAlign: "center",
              padding: "2.5rem",
              borderRadius: 16,
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
            }}
          >
            <h1 style={{ fontSize: "1.5rem", marginBottom: "0.75rem", color: "#f87171" }}>
              Something went wrong
            </h1>
            <p style={{ fontSize: "0.95rem", color: "#94a3b8", marginBottom: "1.5rem" }}>
              An unexpected error occurred. You can try reloading the page.
            </p>
            {this.state.error && (
              <pre
                style={{
                  fontSize: "0.8rem",
                  background: "rgba(0,0,0,0.3)",
                  padding: "1rem",
                  borderRadius: 8,
                  textAlign: "left",
                  overflow: "auto",
                  maxHeight: 120,
                  marginBottom: "1.5rem",
                  color: "#fca5a5",
                }}
              >
                {this.state.error.message}
              </pre>
            )}
            <button
              onClick={this.handleReset}
              style={{
                padding: "0.6rem 1.5rem",
                borderRadius: 8,
                border: "none",
                background: "#7c3aed",
                color: "#fff",
                cursor: "pointer",
                fontSize: "0.95rem",
                fontWeight: 600,
              }}
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
