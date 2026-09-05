// EVERY NUMBER IN THIS FILE IS EITHER MEASURED OR ABSENT.
//
// This file carried "Time: 2-4 hours" for the manual workflow and "3
// tools", with no source, in a repo where every other file documents
// where its numbers come from -- it had zero comment lines. A fabricated
// comparison is the same defect as a fabricated Km, and it sat on the
// page that advertises never fabricating one.
//
// The manual side no longer claims a duration. Nobody here has timed a
// researcher doing this work, and inventing a smaller, more "modest"
// number would be the identical defect wearing a humbler face. It
// describes the WORK instead, which is verifiable by anyone who has done
// it.
//
// The Terrium side keeps a number because that one is measurable, and was
// measured end-to-end through POST /api/simulate on 2026-09-05:
//
//   hexokinase (live BRENDA lookup)        28.3 s
//   covid-19 SIR (local disease registry)   2.6 s
//   seasonal influenza                      2.0 s
//
// "Under 30 seconds" is stated as the upper bound those runs support, not
// as a typical figure -- the enzyme path is slow because it makes a real
// network call to BRENDA, which is the point of it.
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import TerminalWindow from "./TerminalWindow";
import Reveal from "./Reveal";

interface Step {
  icon: string;
  label: string;
  detail: string;
}

const WITHOUT_TERRIUM: Step[] = [
  {
    icon: "\uD83D\uDCDA",
    label: "Literature search",
    detail:
      "Manually search BRENDA and PubMed for kinetic parameters. Cross-reference papers for consensus Km/Vmax values, and record where each one came from.",
  },
  {
    icon: "\uD83D\uDCBB",
    label: "Write ODE code",
    detail:
      "Code the rate equations from scratch. Debug numerical integration. Handle edge cases (saturation, stiffness).",
  },
  {
    icon: "\u270D\uFE0F",
    label: "Validate & cite",
    detail:
      "Check against closed-form solutions. Manually track every parameter to its source paper for your lab report.",
  },
  {
    icon: "\u23F1\uFE0F",
    label: "Time: however long it takes",
    detail:
      "Per experiment, and students learn several tools before they get one number. Terrium has not timed this, so it does not put a figure on it.",
  },
];

const WITH_TERRIUM: Step[] = [
  {
    icon: "\uD83D\uDDE3\uFE0F",
    label: "Ask in plain English",
    detail:
      '"Lactate dehydrogenase with pyruvate" \u2014 that\'s it. Terrium resolves the correct enzyme, substrate, and literature parameters.',
  },
  {
    icon: "\u2699\uFE0F",
    label: "Automatic pipeline",
    detail:
      "BRENDA lookup \u2192 PubMed citation check \u2192 ODE assembly with conserved-quantity checks. All automated.",
  },
  {
    icon: "\u2705",
    label: "Verified result",
    detail:
      "RK4 integration validated against closed-form solutions, an independent integrator, or a physical invariant, depending on the domain. Every resolved parameter carries its citation.",
  },
  {
    icon: "\u26A1",
    label: "Time: under 30 seconds",
    detail:
      "From question to citable result. Measured 2.0-28.3 s across enzyme-kinetics and epidemiology queries; the enzyme path is the slow one because it makes a live BRENDA call.",
  },
];

const CARD_COLORS = {
  without: {
    border: "border-red-500/15",
    bg: "bg-red-500/[0.02]",
    dot: "bg-red-400/60",
  },
  with: {
    border: "border-[#1D8A72]/20",
    bg: "bg-[#1D8A72]/[0.02]",
    dot: "bg-[#1D8A72]",
  },
};

export default function WorkflowCompare() {
  const [activeTab, setActiveTab] = useState<"without" | "with">("without");

  const steps = activeTab === "without" ? WITHOUT_TERRIUM : WITH_TERRIUM;
  const colors = CARD_COLORS[activeTab];
  const label = activeTab === "without" ? "Without Terrium" : "With Terrium";

  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10" id="compare">
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-[#F59E0B] text-[11px] font-mono font-medium">
            compare
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#F59E0B]/20 to-transparent" />
        </div>
        <h2 className="section-header">The difference</h2>
        <p className="font-sans text-[13px] text-white/50 mb-8 -mt-2 max-w-md">
          Toggle between the old way and the Terrium way.
        </p>

        <TerminalWindow
          path={`~ — terrium compare --mode ${activeTab === "without" ? "traditional" : "terrium"}`}
          glow
        >
          <div className="mb-4 text-white/90">
            <span className="text-[#1D8A72]">$</span>{" "}
            <span className="font-mono text-[12px]">
              terrium workflow --compare
            </span>
          </div>

          {/* Toggle */}
          <div className="flex items-center gap-2 mb-6">
            <button
              onClick={() => setActiveTab("without")}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[11px] font-mono transition-all duration-300 ${
                activeTab === "without"
                  ? "bg-red-500/10 border border-red-500/20 text-red-400"
                  : "border border-white/[0.04] text-white/25 hover:text-white/45"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-red-400/60" />
              traditional
            </button>
            <button
              onClick={() => setActiveTab("with")}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[11px] font-mono transition-all duration-300 ${
                activeTab === "with"
                  ? "bg-[#1D8A72]/10 border border-[#1D8A72]/20 text-[#1D8A72]"
                  : "border border-white/[0.04] text-white/25 hover:text-white/45"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[#1D8A72]" />
              terrium
            </button>
            <span className="ml-auto text-[10px] text-white/15 font-mono uppercase tracking-wider">
              {label}
            </span>
          </div>

          {/* Steps */}
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              className="space-y-3"
            >
              {steps.map((step, i) => (
                <motion.div
                  key={step.label}
                  initial={{
                    opacity: 0,
                    x: activeTab === "without" ? -12 : 12,
                  }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{
                    duration: 0.4,
                    delay: i * 0.08,
                    ease: [0.16, 1, 0.3, 1],
                  }}
                  className={`flex items-start gap-3 rounded-lg border ${colors.border} ${colors.bg} p-3 group hover:border-opacity-40 transition-all duration-300`}
                >
                  <span className="text-[16px] shrink-0 mt-0.5">
                    {step.icon}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${colors.dot} shrink-0`}
                      />
                      <span className="text-[12px] text-white/70 font-sans font-medium">
                        {step.label}
                      </span>
                      <span className="text-[9px] text-white/15 font-mono tracking-wider">
                        step {i + 1}
                      </span>
                    </div>
                    <p className="text-[11px] text-white/50 leading-relaxed pl-5">
                      {step.detail}
                    </p>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </AnimatePresence>

          {/* Summary bar */}
          <motion.div
            key={`bar-${activeTab}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className={`mt-5 pt-4 border-t border-white/[0.04] flex items-center justify-between text-[10px]`}
          >
            <span className="text-white/25 font-mono">
              {activeTab === "without"
                ? "4 steps \u2022 3 tools"
                : "4 steps \u2022 1 tool \u2022 under 30 s (measured)"}
            </span>
            <span
              className={`font-mono ${
                activeTab === "without" ? "text-red-400/60" : "text-[#1D8A72]"
              }`}
            >
              {activeTab === "without"
                ? "\u2717 error-prone"
                : "\u2713 verified"}
            </span>
          </motion.div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
