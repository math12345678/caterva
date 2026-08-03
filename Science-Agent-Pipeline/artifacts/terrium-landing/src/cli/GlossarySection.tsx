import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import TerminalWindow from "./TerminalWindow";
import Reveal from "./Reveal";

interface Term {
  id: string;
  term: string;
  symbol?: string | null;
  definition: string;
  category: "math" | "bio" | "epi" | "engine";
}

const CATEGORY_STYLES: Record<
  Term["category"],
  { label: string; color: string; bg: string }
> = {
  math: { label: "math", color: "#3B82F6", bg: "bg-[#3B82F6]/10" },
  bio: { label: "bio", color: "#1D8A72", bg: "bg-[#1D8A72]/10" },
  epi: { label: "epi", color: "#EF4444", bg: "bg-[#EF4444]/10" },
  engine: { label: "engine", color: "#F59E0B", bg: "bg-[#F59E0B]/10" },
};

const TERMS: Term[] = [
  {
    id: "ode",
    term: "Ordinary Differential Equation",
    symbol: "ODE",
    definition:
      "An equation that describes how a quantity changes over time using derivatives. Terrium assembles ODE systems from rate laws (e.g., d[S]/dt = -Vmax·[S]/(Km+[S])) and solves them numerically.",
    category: "math",
  },
  {
    id: "rk4",
    term: "Runge-Kutta 4th Order",
    symbol: "RK4",
    definition:
      "A numerical integration method that computes the next state using a weighted average of four slope estimates. Used by Terrium's engine for high-accuracy ODE solving with 200 substeps per output point.",
    category: "math",
  },
  {
    id: "mm",
    term: "Michaelis-Menten Kinetics",
    symbol: "MM",
    definition:
      "The most common model of enzyme kinetics: the reaction rate v = Vmax·[S]/(Km+[S]). Km is the substrate concentration at half-maximal velocity; Vmax is the maximum rate at saturating substrate.",
    category: "bio",
  },
  {
    id: "km",
    term: "Michaelis Constant",
    symbol: "K\u2098",
    definition:
      "The substrate concentration at which the reaction rate is half of Vmax. Lower Km means higher enzyme-substrate affinity. Terrium sources Km values directly from BRENDA.",
    category: "bio",
  },
  {
    id: "vmax",
    term: "Maximal Velocity",
    symbol: "V\u2098\u2090\u2093",
    definition:
      "The maximum reaction rate achievable when the enzyme is saturated with substrate. Depends on enzyme concentration and catalytic efficiency (kcat).",
    category: "bio",
  },
  {
    id: "sir",
    term: "Susceptible-Infected-Recovered Model",
    symbol: "SIR",
    definition:
      "A compartmental epidemiological model where the population flows from Susceptible (S) → Infected (I) → Recovered (R). Governed by transmission rate β and recovery rate γ. Population N = S+I+R is conserved.",
    category: "epi",
  },
  {
    id: "r0",
    term: "Basic Reproduction Number",
    symbol: "R\u2080",
    definition:
      "The average number of secondary infections caused by one infected individual in a fully susceptible population. R₀ = β/γ. If R₀ > 1, an epidemic occurs; if R₀ < 1, the outbreak fades.",
    category: "epi",
  },
  {
    id: "beta",
    term: "Transmission Rate",
    symbol: "\u03B2",
    definition:
      "The rate at which susceptible individuals become infected upon contact with infected individuals. Units: 1/day. Higher β means faster spread.",
    category: "epi",
  },
  {
    id: "gamma",
    term: "Recovery Rate",
    symbol: "\u03B3",
    definition:
      "The rate at which infected individuals recover (or are removed). 1/γ is the average infectious period in days.",
    category: "epi",
  },
  {
    id: "conserved",
    term: "Conserved Quantity",
    symbol: null,
    definition:
      "A value that remains constant throughout a simulation — e.g., total population N = S+I+R in SIR models, or enzyme mass balance. Terrium checks these invariants at every timestep as a validation signal.",
    category: "engine",
  },
  {
    id: "residual",
    term: "Closed-Form Residual",
    symbol: null,
    definition:
      "The difference between the numerical solution and the exact analytical solution. For Michaelis-Menten: Km·ln(S₀/S) + (S₀ - S) = Vmax·t. A residual near 1e-14 confirms the RK4 solver is correct.",
    category: "engine",
  },
  {
    id: "sbml",
    term: "Systems Biology Markup Language",
    symbol: "SBML",
    definition:
      "An XML-based standard format for representing computational models in systems biology. Terrium exports SBML Level 3 Version 2, compatible with COPASI, Tellurium, and libSBML.",
    category: "engine",
  },
];

const CATEGORIES = ["all", "math", "bio", "epi", "engine"] as const;

export default function GlossarySection() {
  const [openId, setOpenId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");

  const filtered =
    filter === "all" ? TERMS : TERMS.filter((t) => t.category === filter);

  return (
    <section
      className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-blue"
      id="glossary"
    >
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-[#3B82F6] text-[11px] font-mono font-medium">
            glossary
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#3B82F6]/20 to-transparent" />
        </div>
        <h2 className="section-header">Key terms</h2>
        <p className="font-sans text-[13px] text-white/30 mb-8 -mt-2 max-w-sm">
          A quick reference for students and researchers. Click any term to
          expand.
        </p>

        <TerminalWindow path="~ — terrium glossary" glow>
          <div className="mb-4 text-white/90">
            <span className="text-[#1D8A72]">$</span>{" "}
            <span className="font-mono text-[12px]">
              terrium glossary --all
            </span>
          </div>

          {/* Category filter */}
          <div className="flex flex-wrap items-center gap-1.5 mb-5">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setFilter(cat)}
                className={`px-2.5 py-1 rounded-md text-[10px] font-mono transition-all duration-200 ${
                  filter === cat
                    ? "bg-white/[0.06] text-white/80 border border-white/[0.08]"
                    : "text-white/25 hover:text-white/50 border border-transparent"
                }`}
              >
                {cat}
                {cat !== "all" && (
                  <span className="ml-1 text-white/15">
                    ({TERMS.filter((t) => t.category === cat).length})
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Terms list */}
          <div className="space-y-0 divide-y divide-white/[0.04]">
            {filtered.map((term) => {
              const catStyle = CATEGORY_STYLES[term.category];
              const isOpen = openId === term.id;

              return (
                <div key={term.id} className="py-1.5">
                  <button
                    onClick={() => setOpenId(isOpen ? null : term.id)}
                    className="w-full flex items-center gap-3 py-2 text-left group"
                    aria-expanded={isOpen}
                  >
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] uppercase tracking-wider font-mono ${catStyle.bg}`}
                      style={{ color: catStyle.color }}
                    >
                      {catStyle.label}
                    </span>
                    <span className="flex-1 min-w-0">
                      <span className="text-[12px] text-white/70 font-sans group-hover:text-white/90 transition-colors">
                        {term.term}
                      </span>
                      {term.symbol && (
                        <span className="ml-1.5 text-[11px] text-white/25 font-mono">
                          ({term.symbol})
                        </span>
                      )}
                    </span>
                    <motion.span
                      animate={{ rotate: isOpen ? 180 : 0 }}
                      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                      className="text-white/15 text-[10px] shrink-0"
                    >
                      <svg className="w-3 h-3" viewBox="0 0 10 10" fill="none">
                        <path
                          d="M2 3.5L5 6.5L8 3.5"
                          stroke="currentColor"
                          strokeWidth="1.2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </motion.span>
                  </button>

                  <AnimatePresence>
                    {isOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                        className="overflow-hidden"
                      >
                        <p className="pl-[72px] pr-2 pb-3 text-[11px] text-white/40 leading-relaxed">
                          {term.definition}
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>

          <div className="mt-4 pt-3 border-t border-white/[0.04] text-[10px] text-white/15 font-mono">
            {filtered.length} term{filtered.length !== 1 ? "s" : ""}
            {filter !== "all" && ` in ${filter}`}
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
