import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import TerminalWindow from "./TerminalWindow";
import Reveal from "./Reveal";

interface Term {
  id: string;
  term: string;
  symbol?: string | null;
  definition: string;
  category: "math" | "bio" | "md" | "engine";
}

const CATEGORY_STYLES: Record<
  Term["category"],
  { label: string; color: string; bg: string }
> = {
  math: { label: "math", color: "#6A6E78", bg: "bg-muted/10" },
  bio: { label: "bio", color: "#5D7F8D", bg: "bg-signal/10" },
  md: { label: "md", color: "#2A2D35", bg: "bg-fg/10" },
  engine: { label: "engine", color: "#946522", bg: "bg-caution/10" },
};

const TERMS: Term[] = [
  {
    id: "ode",
    term: "Ordinary Differential Equation",
    symbol: "ODE",
    definition:
      "An equation that describes how a quantity changes over time using derivatives. Caterva assembles ODE systems from rate laws (e.g., d[S]/dt = -Vmax·[S]/(Km+[S])) and solves them numerically.",
    category: "math",
  },
  {
    id: "rk4",
    term: "Runge-Kutta 4th Order",
    symbol: "RK4",
    definition:
      "A numerical integration method that computes the next state using a weighted average of four slope estimates. Used by Caterva's engine for high-accuracy ODE solving with 200 substeps per output point.",
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
      "The substrate concentration at which the reaction rate is half of Vmax. Lower Km means higher enzyme-substrate affinity. Caterva sources Km values directly from BRENDA.",
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
    id: "ki",
    term: "Inhibition Constant",
    symbol: "K\u1D62",
    definition:
      "The dissociation constant of an enzyme-inhibitor complex. A competitive inhibitor at concentration [I] raises the apparent Km to Km(1 + [I]/Ki) and leaves Vmax unchanged.",
    category: "bio",
  },
  {
    id: "catalytic-residue",
    term: "Catalytic Residue",
    symbol: null,
    definition:
      "A residue that takes part in the chemistry, as curated by the Mechanism and Catalytic Site Atlas (M-CSA). caterva prepare maps them onto your structure by alignment and ranks every defect by its distance to them.",
    category: "md",
  },
  {
    id: "replica",
    term: "Replica",
    symbol: null,
    definition:
      "An independent run from the same starting structure with different initial velocities. One trajectory is one sample; a spread across replicas is what makes a simulated quantity a result.",
    category: "md",
  },
  {
    id: "block-averaging",
    term: "Block Averaging",
    symbol: null,
    definition:
      "Flyvbjerg and Petersen (1989): averaging a correlated time series in ever longer blocks until its error stops growing. It is how caterva md --summarise tells a converged run from one shorter than its own correlation time.",
    category: "md",
  },
  {
    id: "rmsf",
    term: "Root-Mean-Square Fluctuation",
    symbol: "RMSF",
    definition:
      "How far each residue moves about its average position during a run. caterva analyze compares the active-site pocket with the rest of the protein.",
    category: "md",
  },
  {
    id: "conserved",
    term: "Conserved Quantity",
    symbol: null,
    definition:
      "A value that remains constant throughout a simulation — e.g., molecule count a + c = a0 in a bimolecular SSA, or substrate plus product in Michaelis-Menten. Caterva checks these invariants at every timestep as a validation signal.",
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
      "An XML-based standard format for representing computational models in systems biology. Caterva exports SBML Level 3 Version 2, compatible with COPASI, Caterva, and libSBML.",
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
          <span className="text-muted text-[11px] font-mono font-medium">
            glossary
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-muted/20 to-transparent" />
        </div>
        <h2 className="section-header">Key terms</h2>
        <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2 max-w-sm">
          A quick reference for students and researchers. Click any term to
          expand.
        </p>

        <TerminalWindow path="~ — glossary" glow>
          <div className="mb-4 text-[11px] font-mono text-fg/60">
            # the terms this page and the reports use
          </div>

          {/* Category filter */}
          <div className="flex flex-wrap items-center gap-1.5 mb-5">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setFilter(cat)}
                className={`px-2.5 py-1 rounded-md text-[10px] font-mono transition-all duration-200 ${
                  filter === cat
                    ? "bg-fg/[0.06] text-fg/85 border border-fg/[0.16]"
                    : "text-fg/66 hover:text-fg/76 border border-transparent"
                }`}
              >
                {cat}
                {cat !== "all" && (
                  <span className="ml-1 text-fg/66">
                    ({TERMS.filter((t) => t.category === cat).length})
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Terms list */}
          <div className="space-y-0 divide-y divide-fg/[0.04]">
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
                      <span className="text-[12px] text-fg/78 font-sans group-hover:text-fg/92 transition-colors">
                        {term.term}
                      </span>
                      {term.symbol && (
                        <span className="ml-1.5 text-[11px] text-fg/66 font-mono">
                          ({term.symbol})
                        </span>
                      )}
                    </span>
                    <motion.span
                      animate={{ rotate: isOpen ? 180 : 0 }}
                      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                      className="text-fg/66 text-[10px] shrink-0"
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
                        <p className="pl-[72px] pr-2 pb-3 text-[11px] text-fg/70 leading-relaxed">
                          {term.definition}
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>

          <div className="mt-4 pt-3 border-t border-fg/[0.08] text-[10px] text-fg/66 font-mono">
            {filtered.length} term{filtered.length !== 1 ? "s" : ""}
            {filter !== "all" && ` in ${filter}`}
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
