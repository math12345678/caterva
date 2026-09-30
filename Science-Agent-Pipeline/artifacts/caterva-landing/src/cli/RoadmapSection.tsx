import { motion } from "framer-motion";
import Reveal from "./Reveal";
import TerminalWindow from "./TerminalWindow";

// Rewritten 2026-09-29 against the repository and the v0.4.0 tag. The
// previous list had a "Classroom Pilot Program" in progress (there is no
// pilot), dated quarters for a batch API and for SBML export (SBML export
// shipped in v0.4.0; nothing has a date), Helm charts under exploration,
// every MD tool as "Live" although no release carries them, and the Ki
// comparison as "Planned" although it is built. Statuses now say where a
// thing is: in a release, on the main branch, or planned with no date.
interface Milestone {
  id: string;
  title: string;
  desc: string;
  status: "released" | "main" | "planned";
  icon: string;
  color: string;
}

const MILESTONES: Milestone[] = [
  {
    id: "compose",
    title: "Enzyme Models with Cited Constants",
    desc: "caterva compose: Michaelis-Menten, inhibition and composed mechanisms, with Km, kcat and Ki from BRENDA and a labelled placeholder wherever none was found.",
    status: "released",
    icon: "\u{1F9EC}",
    color: "#5D7F8D",
  },
  {
    id: "exports",
    title: "SBML, Antimony, CSV and Methods Export",
    desc: "caterva compose --export: every number carries its origin into the file, including what its source row measured and how far the other rows disagree.",
    status: "released",
    icon: "\u{1F4E6}",
    color: "#5D7F8D",
  },
  {
    id: "right-row",
    title: "Constants from the Right Row",
    desc: "caterva compose --isoform, and a Ki taken from a row of the model's own inhibition mode: a constant BRENDA holds only for another isoform or another mechanism is refused, naming what exists, rather than filled with a different protein's or mechanism's value.",
    status: "main",
    icon: "\u{1F3AF}",
    color: "#946522",
  },
  {
    id: "stochastic",
    title: "Exact Stochastic Kinetics",
    desc: "caterva sim: Gillespie SSA for first-order decay, bimolecular association and replicate ensembles, each checked against its closed form.",
    status: "released",
    icon: "\u{1F3B2}",
    color: "#5D7F8D",
  },
  {
    id: "structure-audit",
    title: "Structure Preparation Audit",
    desc: "caterva prepare: sequence differences, chain breaks, truncated side chains and uncertain protonation states, ranked by distance to the M-CSA catalytic residues.",
    status: "main",
    icon: "\u{1F52C}",
    color: "#946522",
  },
  {
    id: "md-replicas",
    title: "GROMACS Setup and Replicas",
    desc: "caterva md at the assay conditions of a cited constant, three replicas by default, and a convergence verdict from block averaging.",
    status: "main",
    icon: "\u269B",
    color: "#946522",
  },
  {
    id: "enzyme-analysis",
    title: "Enzyme Trajectory Analysis",
    desc: "caterva analyze: catalytic distances and angles, hydrogen bonds, chi1 rotamers, active-site water and flexibility against the crystal, read natively from .xtc, equal to gmx distance, gangle, hbond, angle and select on real frames, and reported only when the replicas agree.",
    status: "main",
    icon: "\u{1F4CF}",
    color: "#946522",
  },
  {
    id: "ki-bridge",
    title: "Binding Free Energy against a Cited Ki",
    desc: "caterva bind, complex and fep: an absolute binding free energy run at the assay temperature of a cited Ki and judged against it. Built, and not yet shown to reproduce a measured Ki.",
    status: "main",
    icon: "\u2696",
    color: "#946522",
  },
  {
    id: "ligands",
    title: "Ligands with Provenance",
    desc: "Parameterise bound substrates and inhibitors with GAFF2 or OpenFF, recording the charge method, and show where the two disagree. Today the ligand topology is yours to supply.",
    status: "planned",
    icon: "\u{1F9EA}",
    color: "#6A6E78",
  },
  {
    id: "sbml-import",
    title: "SBML Import",
    desc: "Read an existing SBML model and resolve its constants the way compose does.",
    status: "planned",
    icon: "\u{1F4E5}",
    color: "#6A6E78",
  },
];

const STATUS_CONFIG: Record<
  Milestone["status"],
  { label: string; bg: string; text: string; dot: string }
> = {
  released: {
    label: "In v0.4.0",
    bg: "bg-signal/15",
    text: "text-signal",
    dot: "bg-signal",
  },
  main: {
    label: "On main",
    bg: "bg-caution/10",
    text: "text-caution/80",
    dot: "bg-caution/60",
  },
  planned: {
    label: "Planned",
    bg: "bg-fg/[0.04]",
    text: "text-fg/70",
    dot: "bg-fg/20",
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
          <span className="text-muted text-[11px] font-mono font-medium">
            ROADMAP
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-muted/20 to-transparent" />
        </div>
        <h2 className="section-header">What exists, and what is next</h2>
        <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2 max-w-md">
          Where each tool is today: in a release, on the main branch, or
          planned with no date.
        </p>

        <TerminalWindow path="~ — roadmap" glow>
          <div className="mb-4 text-[11px] font-mono text-fg/60">
            # released, built, planned
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
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] tracking-wide ${cfg.bg} ${cfg.text}`}
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
                  "linear-gradient(to bottom, rgba(106,110,120,0.3), rgba(106,110,120,0.15), rgba(106,110,120,0.1), transparent)",
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
                          className="text-[14px] font-sans font-medium transition-colors group-hover:text-fg/92"
                          style={{ color: m.color }}
                        >
                          {m.title}
                        </h3>
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9px] tracking-wide ${cfg.bg} ${cfg.text}`}
                        >
                          {cfg.label}
                        </span>
                      </div>
                      <p className="text-[12px] text-fg/70 leading-relaxed group-hover:text-fg/70 transition-colors">
                        {m.desc}
                      </p>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-fg/[0.08] flex items-center gap-3 text-[11px] text-fg/66">
            <span className="text-muted">?</span>
            <span>
              Have a feature request?{" "}
              <a
                href="mailto:admin.terrium@gmail.com"
                className="text-muted/60 hover:text-muted transition-colors"
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
