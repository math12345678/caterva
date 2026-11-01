import { motion } from "framer-motion";
import TerminalWindow from "./TerminalWindow";
import Reveal from "./Reveal";

// Where Caterva's numbers come from, and what runs where.
//
// This panel was "caterva status --all", a command that does not exist,
// over a green status dot on a list that was never checked, beside an
// uptime and a waitlist count fetched from an API a static page does not
// have. It also said BRENDA supplies Vmax, which Caterva never looks up:
// Vmax is kcat times the enzyme concentration you set (ADR 0013/0019).
//
// Each entry below is a host the code calls, read from the source on
// 2026-09-29 (Tests/enzyme_lookup.py, caterva/prepare, caterva/structure),
// and says what that service supplies and what it does not.
interface Source {
  name: string;
  where: string;
  supplies: string;
}

const REMOTE: Source[] = [
  {
    name: "BRENDA",
    where: "brenda-enzymes.org",
    supplies:
      "Km, kcat and Ki rows, each with its organism, reference and the row's own commentary. Vmax is never looked up: it is kcat times the enzyme concentration you set.",
  },
  {
    name: "UniProt",
    where: "rest.uniprot.org",
    supplies:
      "Which protein an EC number and organism name, and the sequence a structure is checked against.",
  },
  {
    name: "PubChem",
    where: "pubchem.ncbi.nlm.nih.gov",
    supplies: "Other names for a compound, so one substance named two ways is recognised.",
  },
  {
    name: "PubMed and CORE",
    where: "eutils.ncbi.nlm.nih.gov · core.ac.uk",
    supplies:
      "Papers to read when BRENDA holds no value. Candidates for a person to check, never a number.",
  },
  {
    name: "RCSB PDB",
    where: "files.rcsb.org",
    supplies: "Structures for the preparation audit and the molecular dynamics setup.",
  },
];

const LOCAL: Source[] = [
  {
    name: "Caterva engine",
    where: "your machine",
    supplies: "ODE and stochastic simulation (libRoadRunner), analysis, and the free-energy estimators.",
  },
  {
    name: "GROMACS",
    where: "your machine",
    supplies:
      "Molecular dynamics. Caterva writes the inputs and reads the trajectories; GROMACS runs the physics.",
  },
];

function SourceRow({ s, i }: { s: Source; i: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, delay: i * 0.05, ease: [0.22, 1, 0.36, 1] }}
      className="grid grid-cols-1 sm:grid-cols-[9.5rem_1fr] gap-x-4 gap-y-0.5 py-2.5 border-b border-fg/[0.06] last:border-b-0"
    >
      <div className="min-w-0">
        <div className="text-[12px] text-fg/88 font-sans font-medium">{s.name}</div>
        <div className="text-[10px] text-fg/60 font-mono break-words">{s.where}</div>
      </div>
      <p className="text-[11px] text-fg/74 leading-relaxed">{s.supplies}</p>
    </motion.div>
  );
}

export default function LiveStatusPanel() {
  return (
    <section
      className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-blue"
      id="status"
    >
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-muted text-[11px] font-mono font-medium">
            sources
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-muted/20 to-transparent" />
        </div>
        <h2 className="section-header">Where the numbers come from</h2>
        <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2 max-w-md">
          Every service Caterva calls, what it supplies, and what it does not.
        </p>

        <TerminalWindow path="~ — sources" glow>
          <div className="mb-3 text-[11px] font-mono text-fg/60">
            # looked up over the network
          </div>
          <div className="mb-5">
            {REMOTE.map((s, i) => (
              <SourceRow key={s.name} s={s} i={i} />
            ))}
          </div>
          <div className="mb-3 text-[11px] font-mono text-fg/60">
            # computed on the machine that asks
          </div>
          <div>
            {LOCAL.map((s, i) => (
              <SourceRow key={s.name} s={s} i={i + REMOTE.length} />
            ))}
          </div>

          <div className="mt-4 pt-3 border-t border-fg/[0.08] space-y-1 text-[10px] text-fg/60 font-mono">
            <p>
              KEGG support is off by default: its licence terms need an
              operator's agreement, given by setting CATERVA_ENABLE_KEGG.
            </p>
            <p>A list, not a live check. Read from the source code on 2026-09-29.</p>
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
