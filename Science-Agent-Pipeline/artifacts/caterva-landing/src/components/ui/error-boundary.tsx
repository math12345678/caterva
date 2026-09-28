import { Component, type ReactNode, type ErrorInfo } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
  info: ErrorInfo | null;
  copied: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null, info: null, copied: false };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error, info: null };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.setState({ info });
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ error: null, info: null, copied: false });
  };

  handleCopyError = () => {
    const text = [
      `Error: ${this.state.error?.message || "Unknown error"}`,
      this.state.info?.componentStack || "",
    ].join("\n\n");
    navigator.clipboard
      .writeText(text)
      .then(() => {
        this.setState({ copied: true });
        setTimeout(() => this.setState({ copied: false }), 2000);
      })
      .catch(() => {});
  };

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="min-h-screen bg-surface flex items-center justify-center p-6">
          <div className="max-w-md text-center">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-500/10 mb-5">
              <span className="text-red-400 text-lg">!</span>
            </div>
            <h1 className="text-fg/85 text-[16px] font-sans font-medium mb-2">
              Something went wrong
            </h1>
            <p className="text-fg/70 text-[13px] font-sans mb-8 leading-relaxed">
              {this.state.error.message || "An unexpected error occurred."}
            </p>
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={this.handleReset}
                className="inline-flex items-center gap-2 rounded-xl border border-signal/30 bg-signal/[0.06] px-5 py-2.5 text-[13px] text-signal transition-all duration-300 hover:bg-signal/[0.10]"
              >
                try again
              </button>
              <button
                onClick={this.handleCopyError}
                className="inline-flex items-center gap-2 rounded-xl border border-fg/[0.16] px-5 py-2.5 text-[12px] text-fg/70 transition-all duration-300 hover:border-fg/[0.30] hover:text-fg/80"
              >
                {this.state.copied ? "copied" : "copy error"}
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
