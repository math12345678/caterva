import type { ReactNode } from "react";

interface TerminalWindowProps {
  path: string;
  children: ReactNode;
  className?: string;
  glow?: boolean;
}

export default function TerminalWindow({
  path,
  children,
  className = "",
  glow = false,
}: TerminalWindowProps) {
  // An ink slab on paper: the terminal is the page's one solid shape, the
  // way the mark's dots are. `.ink-surface` flips every fg/surface/signal
  // token inside it, so children keep their classes and read correctly.
  return (
    <div
      className={`ink-surface relative rounded-lg overflow-hidden font-mono ${
        glow ? "ring-1 ring-signal/40" : ""
      } ${className}`}
    >
      <div className="flex items-center gap-2 border-b border-fg/[0.10] px-4 py-2.5">
        <div className="flex gap-1.5" aria-hidden="true">
          <span className="h-2 w-2 rounded-full bg-fg/30" />
          <span className="h-2 w-2 rounded-full bg-fg/30" />
          <span className="h-2 w-2 rounded-full bg-signal" />
        </div>
        <span className="ml-2 text-[11px] text-fg/70 tracking-wide">{path}</span>
      </div>
      <div className="p-5 md:p-6 text-[13px] md:text-[14px] leading-relaxed relative">
        {children}
      </div>
    </div>
  );
}
