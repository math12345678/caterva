import { motion } from "framer-motion";
import Magnetic from "@/components/ui/Magnetic";

export default function NotFound() {
  return (
    <main
      className="min-h-screen bg-[#0A0E0C] text-white/90 font-sans flex items-center justify-center p-4 dot-grid-bg"
      role="main"
    >
      <h1 className="sr-only">404 — Page Not Found | Terrium</h1>
      {/* Ambient glows */}
      <div
        className="fixed top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] pointer-events-none z-0 opacity-30"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(29,138,114,0.08), transparent 60%)",
        }}
      />
      <div
        className="fixed bottom-0 right-0 w-[600px] h-[400px] pointer-events-none z-0 opacity-20"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(245,158,11,0.04), transparent 60%)",
        }}
      />

      {/* Main content */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="relative z-10 w-full max-w-md"
      >
        {/* Terminal window */}
        <div
          className="rounded-xl border border-white/[0.08] bg-[#0A0E0C]/90 backdrop-blur-xl overflow-hidden"
          style={{ boxShadow: "0 0 60px rgba(29,138,114,0.08)" }}
        >
          {/* Title bar */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.05] bg-[#0A0E0C]/80">
            <div className="flex gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500/50" />
              <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/50" />
              <span className="w-2.5 h-2.5 rounded-full bg-green-500/50" />
            </div>
            <span className="flex-1 text-center text-[10px] font-mono text-white/20 uppercase tracking-widest">
              404 — page not found
            </span>
          </div>

          {/* Body */}
          <div className="p-6">
            {/* ASCII art */}
            <pre className="text-[#1D8A72]/40 text-[10px] leading-tight font-mono mb-6 select-none">
              {`  ┌──────────────────────────┐
  │  TERRIUM v0.7.0          │
  │  status: route not found │
  │  exit code: 404          │
  └──────────────────────────┘`}
            </pre>

            <div className="mb-5">
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-[#1D8A72] font-mono text-[12px]">$</span>
                <span className="text-white/35 font-mono text-[12px]">
                  terrium route --resolve /this/path
                </span>
              </div>
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
                className="text-[#F59E0B]/80 font-mono text-[11px] mb-1"
              >
                Error: route not found in simulation graph
              </motion.p>
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5 }}
                className="text-white/30 text-[12px] font-sans"
              >
                The page you requested doesn&apos;t exist. It may have been
                moved, renamed, or never created.
              </motion.p>
            </div>

            {/* Suggestions */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7 }}
              className="space-y-2 mb-6"
            >
              <p className="text-[10px] text-white/20 uppercase tracking-wide font-medium mb-3">
                Try one of these:
              </p>
              {[
                {
                  label: "Home — landing page",
                  href: "/",
                  desc: "Ask a question, get a verified simulation",
                },
                {
                  label: "Agent — try the demo",
                  href: "/#agent",
                  desc: "Describe your experiment in plain language",
                },
                {
                  label: "Waitlist — join the pilot",
                  href: "/#waitlist",
                  desc: "Pre-launch spots available",
                },
              ].map((link, i) => (
                <motion.a
                  key={link.href}
                  href={link.href}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.8 + i * 0.08 }}
                  className="group flex items-start gap-3 rounded-lg border border-white/[0.04] bg-white/[0.01] p-3 hover:border-[#1D8A72]/20 hover:bg-[#1D8A72]/[0.02] transition-all duration-300"
                >
                  <span className="shrink-0 w-6 h-6 rounded bg-[#1D8A72]/10 flex items-center justify-center text-[10px] text-[#1D8A72]/70 group-hover:text-[#1D8A72] transition-colors font-mono">
                    {(i + 1).toString().padStart(2, "0")}
                  </span>
                  <div>
                    <span className="text-[13px] text-white/60 group-hover:text-white/80 transition-colors block font-sans">
                      {link.label}
                    </span>
                    <span className="text-[10px] text-white/25 group-hover:text-white/35 transition-colors">
                      {link.desc}
                    </span>
                  </div>
                  <svg
                    className="w-3 h-3 text-white/15 group-hover:text-[#1D8A72] transition-colors shrink-0 ml-auto mt-1"
                    viewBox="0 0 12 12"
                    fill="none"
                  >
                    <path
                      d="M2 6h7M6 2l4 4-4 4"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </motion.a>
              ))}
            </motion.div>

            {/* Primary CTA */}
            <Magnetic strength={0.12}>
              <a
                href="/"
                className="inline-flex items-center gap-2 rounded-lg border border-[#1D8A72]/30 bg-[#1D8A72]/[0.08] px-5 py-2.5 text-[13px] text-[#1D8A72] font-medium transition-all duration-300 hover:bg-[#1D8A72]/[0.14] hover:shadow-[0_0_25px_rgba(29,138,114,0.15)]"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 12 12" fill="none">
                  <path
                    d="M8 2L3 7M3 7l5 3M3 7h6"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                Return home
              </a>
            </Magnetic>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-[10px] text-white/15 mt-4 font-mono">
          exit code 404 —{" "}
          <a
            href="mailto:admin.terrium@gmail.com"
            className="text-white/25 hover:text-white/50 transition-colors"
          >
            admin.terrium@gmail.com
          </a>
        </p>
      </motion.div>
    </main>
  );
}
