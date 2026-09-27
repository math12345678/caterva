import { motion } from "framer-motion";
import Reveal from "./Reveal";
import TerminalWindow from "./TerminalWindow";

interface Milestone {
  id: string;
  title: string;
  desc: string;
  status: "live" | "in-progress" | "planned" | "exploring";
  eta?: string;
  icon: string;
  color: string;
}

const MILESTONES: Milestone[] = [
  {
    id: "classroom-pilot",
    title: "Classroom Pilot Program",
    desc: "First cohort of university teaching labs using Caterva for enzyme kinetics and epidemiology coursework.",
    status: "in-progress",
    eta: "Fall 2026",
    icon: "\u{1F393}",
    color: "#1D8A72",
  },
  {
    id: "pcr-domain",
    title: "PCR Amplification Domain",
    desc: "PCR cycle simulation — exact closed-form growth, plateau modeling, mutation-verified.",
    status: "live",
    icon: "\u{1F9EC}",
    color: "#3B82F6",
  },
  {
    id: "batch-api",
    title: "Batch Simulation API",
    desc: "Submit multiple simulation queries at once. Ideal for parameter sweeps and sensitivity analysis.",
    status: "planned",
    eta: "Q1 2027",
    icon: "\u2699",
    color: "#F59E0B",
  },
  {
    id: "monte-carlo",
    title: "Monte Carlo / Stochastic Solver",
    desc: "Gillespie SSA (decay, bimolecular association, replicate ensembles) and Monte Carlo estimation — stochastic simulation for small-number regimes.",
    status: "live",
    icon: "\u{1F3B2}",
    color: "#8B5CF6",
  },
  {
    id: "population-genetics",
    title: "Population Genetics Domain",
    desc: "Wright-Fisher drift and selection, plus two-locus linkage disequilibrium.",
    status: "live",
    icon: "\u{1F9EC}",
    color: "#EC4899",
  },
  {
    id: "sbml-export",
    title: "SBML Import & Export",
    desc: "Interoperate with the broader systems biology ecosystem. Import existing SBML models, export Caterva runs.",
    status: "planned",
    eta: "Q3 2027",
    icon: "\u{1F4E6}",
    color: "#F97316",
  },
  {
    id: "self-hosted",
    title: "Self-Hosted Deployment",
    desc: "Docker Compose + Kubernetes Helm charts for universities wanting on-premise deployment.",
    status: "exploring",
    icon: "\u{1F3D7}",
    color: "#06B6D4",
  },
  {
    id: "molecular-dynamics",
    title: "Molecular Dynamics Setup",
    desc: "Natural-language configuration of MD simulations — force fields, solvation, and equilibration, already live for Lennard-Jones clusters.",
    status: "live",
    icon: "\u269B",
    color: "#10B981",
  },
];

const STATUS_CONFIG: Record<
  Milestone["status"],
  { label: string; bg: string; text: string; dot: string }
> = {
  live: {
    label: "Live",
    bg: "bg-[#1D8A72]/15",
    text: "text-[#1D8A72]",
    dot: "bg-[#1D8A72]",
  },
  "in-progress": {
    label: "In Progress",
    bg: "bg-[#3B82F6]/15",
    text: "text-[#3B82F6]",
    dot: "bg-[#3B82F6] animate-pulse",
  },
  planned: {
    label: "Planned",
    bg: "bg-[#F59E0B]/10",
    text: "text-[#F59E0B]/80",
    dot: "bg-[#F59E0B]/60",
  },
  exploring: {
    label: "Exploring",
    bg: "bg-white/[0.04]",
    text: "text-white/35",
    dot: "bg-white/20",
  },
};

export default function RoadmapSection() {
  return (
    <section
      className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-blue scroll-mt-16"
      id="roadmap"
    >
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-[#3B82F6] text-[11px] font-mono font-medium">
            ROADMAP
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#3B82F6]/20 to-transparent" />
        </div>
        <h2 className="section-header">What's coming next</h2>
        <p className="font-sans text-[13px] text-white/50 mb-8 -mt-2 max-w-sm">
          Our public roadmap. Everything we're building, in the open.
        </p>

        <TerminalWindow path="~ — caterva roadmap --list" glow>
          <div className="mb-4 text-white/90">
            <span className="text-[#1D8A72]">$</span> caterva roadmap --list
            --sort=status
          </div>

          {/* Status legend */}
          <div className="flex flex-wrap gap-3 mb-6">
            {(
              Object.entries(STATUS_CONFIG) as [
                Milestone["status"],
                (typeof STATUS_CONFIG)[Milestone["status"]],
              ][]
            ).map(([key, cfg]) => (
              <span
                key={key}
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] uppercase tracking-wide ${cfg.bg} ${cfg.text}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                {cfg.label}
              </span>
            ))}
          </div>

          {/* Timeline */}
          <div className="relative">
            {/* Vertical line */}
            <div
              className="absolute left-[19px] top-2 bottom-2 w-px"
              style={{
                background:
                  "linear-gradient(to bottom, rgba(59,130,246,0.3), rgba(59,130,246,0.15), rgba(139,92,246,0.1), transparent)",
              }}
            />

            <div className="space-y-0">
              {MILESTONES.map((m, i) => {
                const cfg = STATUS_CONFIG[m.status];
                return (
                  <motion.div
                    key={m.id}
                    initial={{ opacity: 0, x: -12 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{
                      duration: 0.4,
                      delay: i * 0.06,
                      ease: [0.16, 1, 0.3, 1],
                    }}
                    className="relative flex gap-4 pb-6 last:pb-0 group"
                  >
                    {/* Timeline dot */}
                    <div className="relative z-10 shrink-0 mt-1">
                      <div
                        className="w-[10px] h-[10px] rounded-full border-2 transition-all duration-300 group-hover:scale-125"
                        style={{
                          backgroundColor: `${m.color}20`,
                          borderColor: m.color,
                          boxShadow: `0 0 8px ${m.color}30`,
                        }}
                      />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0 pt-0.5">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className="text-[16px]" aria-hidden="true">
                          {m.icon}
                        </span>
                        <h3
                          className="text-[14px] font-sans font-medium transition-colors group-hover:text-white/90"
                          style={{ color: m.color }}
                        >
                          {m.title}
                        </h3>
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9px] uppercase tracking-wide ${cfg.bg} ${cfg.text}`}
                        >
                          {cfg.label}
                        </span>
                        {m.eta && (
                          <span className="text-[10px] text-white/20 font-mono">
                            {m.eta}
                          </span>
                        )}
                      </div>
                      <p className="text-[12px] text-white/35 leading-relaxed group-hover:text-white/45 transition-colors">
                        {m.desc}
                      </p>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-white/[0.04] flex items-center gap-3 text-[11px] text-white/25">
            <span className="text-[#3B82F6]">?</span>
            <span>
              Have a feature request?{" "}
              <a
                href="mailto:admin.terrium@gmail.com"
                className="text-[#3B82F6]/60 hover:text-[#3B82F6] transition-colors"
              >
                admin.terrium@gmail.com
              </a>{" "}
              &mdash; we build in the open.
            </span>
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
