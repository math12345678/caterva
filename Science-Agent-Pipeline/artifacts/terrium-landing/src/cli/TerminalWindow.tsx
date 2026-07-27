import type { ReactNode } from 'react';

interface TerminalWindowProps {
  path: string;
  children: ReactNode;
  className?: string;
  glow?: boolean;
}

export default function TerminalWindow({ path, children, className = '', glow = false }: TerminalWindowProps) {
  return (
    <div
      className={`relative rounded-xl border bg-black/50 backdrop-blur-sm overflow-hidden font-mono transition-all duration-700 ${
        glow
          ? 'border-[#1D8A72]/20 shadow-[0_0_60px_-15px_rgba(29,138,114,0.25)] hover:shadow-[0_0_80px_-10px_rgba(29,138,114,0.3)]'
          : 'border-white/[0.06] hover:border-white/[0.10]'
      } ${className}`}
    >
      {glow && (
        <div className="absolute top-0 left-0 right-0 h-20 bg-gradient-to-b from-[#1D8A72]/[0.04] to-transparent pointer-events-none" />
      )}
      <div className="flex items-center gap-2 border-b border-white/[0.04] bg-white/[0.015] px-4 py-2.5 relative">
        <div className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f56] transition-opacity hover:opacity-80" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e] transition-opacity hover:opacity-80" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#27c93f] transition-opacity hover:opacity-80" />
        </div>
        <span className="ml-2 text-[11px] text-white/30 tracking-wide">{path}</span>
      </div>
      <div className="p-5 md:p-6 text-[13px] md:text-[14px] leading-relaxed relative">
        {children}
      </div>
    </div>
  );
}
