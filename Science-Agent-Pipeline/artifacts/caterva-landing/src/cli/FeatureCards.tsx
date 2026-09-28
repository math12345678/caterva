import { motion } from "framer-motion";
import Reveal from "./Reveal";
import TerminalWindow from "./TerminalWindow";

const FEATURES = [
  {
    step: "01",
    icon: "⌘",
    title: "Natural Language",
    desc: "Ask in plain English. The LLM resolves your query into structured simulation parameters with full provenance.",
  },
  {
    step: "02",
    icon: "⌂",
    title: "ODE Engine",
    desc: "Powered by Caterva. RK4 integration with conserved-quantity checks and numerical error bounds on every run.",
  },
  {
    step: "03",
    icon: "◉",
    title: "Literature-Grounded",
    desc: "Every parameter traces to a BRENDA or PubMed citation. No black-box numbers.",
  },
  {
    step: "04",
    icon: "∞",
    title: "Real-time Feedback",
    desc: "Watch simulations stream live via SSE. Inspect trajectories, export CSV, re-run with tweaked params.",
  },
];

export default function FeatureCards() {
  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10">
      <Reveal>
        <div className="flex items-center gap-3 text-[10px] text-fg/66 uppercase tracking-widest mb-6">
          <span className="w-5 h-px bg-fg/[0.06]" />
          <span>features</span>
          <span className="flex-1 h-px bg-fg/[0.06]" />
        </div>
        <TerminalWindow path="~ — caterva features --list">
          <div className="mb-4 text-fg/92">
            <span className="text-signal">$</span> caterva features --list
          </div>
          <div className="space-y-0">
            {FEATURES.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{
                  duration: 0.4,
                  delay: i * 0.06,
                  ease: [0.16, 1, 0.3, 1],
                }}
                className="group flex gap-4 py-3 border-b border-fg/[0.06] last:border-0"
              >
                <div className="shrink-0 w-8 h-8 rounded-lg bg-fg/[0.03] border border-fg/[0.10] flex items-center justify-center text-[14px] text-fg/70 group-hover:text-signal group-hover:border-signal/20 transition-all duration-300">
                  {f.icon}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[10px] text-fg/66 font-mono">
                      {f.step}
                    </span>
                    <span className="text-[13px] text-fg/85 font-sans font-medium group-hover:text-fg transition-colors">
                      {f.title}
                    </span>
                  </div>
                  <p className="text-[11px] text-fg/76 leading-relaxed">
                    {f.desc}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
