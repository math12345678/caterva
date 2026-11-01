import { motion } from "framer-motion";
import Magnetic from "@/components/ui/Magnetic";

export default function NotFound() {
  return (
    <main
      className="min-h-screen bg-surface text-fg/92 font-sans flex items-center justify-center p-4 dot-grid-bg"
      role="main"
    >
      <h1 className="sr-only">404 — Page Not Found | Caterva</h1>
      {/* Ambient glows */}
      <div
        className="fixed top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] pointer-events-none z-0 opacity-30"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(93,127,141,0.08), transparent 60%)",
        }}
      />
      <div
        className="fixed bottom-0 right-0 w-[600px] h-[400px] pointer-events-none z-0 opacity-20"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(148,101,34,0.04), transparent 60%)",
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
          className="rounded-xl border border-fg/[0.16] bg-surface/90 backdrop-blur-xl overflow-hidden"
          style={{ boxShadow: "0 0 60px rgba(93,127,141,0.08)" }}
        >
          {/* Title bar */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-fg/[0.10] bg-surface/80">
            <div className="flex gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500/50" />
              <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/50" />
              <span className="w-2.5 h-2.5 rounded-full bg-green-500/50" />
            </div>
            <span className="flex-1 text-center text-[10px] font-mono text-fg/66 uppercase tracking-widest">
              404 — page not found
            </span>
          </div>

          {/* Body */}
          <div className="p-6">
            {/* ASCII art */}
            <pre className="text-signal/40 text-[10px] leading-tight font-mono mb-6 select-none">
              {`  ┌──────────────────────────┐
  │  CATERVA v0.7.0          │
  │  status: route not found │
  │  exit code: 404          │
  └──────────────────────────┘`}
            </pre>

            <div className="mb-5">
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-signal font-mono text-[12px]">$</span>
                <span className="text-fg/70 font-mono text-[12px]">
                  caterva route --resolve /this/path
                </span>
              </div>
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
                className="text-caution/80 font-mono text-[11px] mb-1"
              >
                Error: route not found in simulation graph
              </motion.p>
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5 }}
                className="text-fg/70 text-[12px] font-sans"
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
              <p className="text-[10px] text-fg/66 uppercase tracking-wide font-medium mb-3">
                Try one of these:
              </p>
              {[
                {
                  label: "Home — landing page",
                  href: "/",
                  desc: "Write one line, get cited constants",
                },
                {
                  label: "Agent",
                  href: "/#agent",
                  desc: "Describe your experiment in plain language",
                },
                {
                  label: "Get Caterva",
                  href: "/#get",
                  desc: "Download v0.4.0 or build from the main branch",
                },
              ].map((link, i) => (
                <motion.a
                  key={link.href}
                  href={link.href}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.8 + i * 0.08 }}
                  className="group flex items-start gap-3 rounded-lg border border-fg/[0.08] bg-fg/[0.01] p-3 hover:border-signal/20 hover:bg-signal/[0.02] transition-all duration-300"
                >
                  <span className="shrink-0 w-6 h-6 rounded bg-signal/10 flex items-center justify-center text-[10px] text-signal/70 group-hover:text-signal transition-colors font-mono">
                    {(i + 1).toString().padStart(2, "0")}
                  </span>
                  <div>
                    <span className="text-[13px] text-fg/80 group-hover:text-fg/85 transition-colors block font-sans">
                      {link.label}
                    </span>
                    <span className="text-[10px] text-fg/66 group-hover:text-fg/70 transition-colors">
                      {link.desc}
                    </span>
                  </div>
                  <svg
                    className="w-3 h-3 text-fg/66 group-hover:text-signal transition-colors shrink-0 ml-auto mt-1"
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
                className="inline-flex items-center gap-2 rounded-lg border border-signal/30 bg-signal/[0.08] px-5 py-2.5 text-[13px] text-signal font-medium transition-all duration-300 hover:bg-signal/[0.14]"
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
        <p className="text-center text-[10px] text-fg/66 mt-4 font-mono">
          exit code 404 —{" "}
          <a
            href="mailto:admin.terrium@gmail.com"
            className="text-fg/66 hover:text-fg/76 transition-colors"
          >
            admin.terrium@gmail.com
          </a>
        </p>
      </motion.div>
    </main>
  );
}
