import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import Reveal from "./Reveal";
import TerminalWindow from "./TerminalWindow";

// Rewritten 2026-09-29 against the repository. The previous answers
// described a hosted "platform" with pilot spots, a waitlist "typically 1-2
// weeks", planned paid tiers, a private repository and fifteen domains. The
// repository is public, nothing is priced, and the non-enzyme
// domains were archived on 2026-09-27.
const FAQS = [
  {
    id: "what-is-caterva",
    q: "What is Caterva?",
    a: "Free, open-source software (Apache-2.0) for enzyme kinetics and molecular dynamics, run on your own machine. `caterva compose` builds an enzyme model from a one-line description and looks up Km, kcat and Ki in BRENDA, giving each value's reference, organism and assay conditions; a constant it cannot find stays a labelled placeholder. `caterva sim` runs exact stochastic kinetics. On the main branch, `prepare`, `md`, `analyze`, `bind`, `complex` and `fep` audit a structure, set up GROMACS, analyse the trajectories and hold a binding free energy to a cited Ki.",
  },
  {
    id: "how-accurate",
    q: "How accurate are the simulations?",
    a: "Every solver is checked against something that is not itself: an exact closed-form solution, an independent integrator (scipy's solve_ivp, which shares no code with roadrunner), or a physical invariant tested across the input space with Hypothesis. That shows the equations are solved correctly. It is not validation against experiment: a model is as good as its constants, and the report says which were measured, which were chosen and which are placeholders nobody measured. The free-energy pipeline (`caterva fep`) has not yet been shown to reproduce a measured Ki, and it takes the ligand's force-field parameters from you rather than generating them.",
  },
  {
    id: "no-code",
    q: "Do I need to write code?",
    a: 'No programming, but it is a command-line tool. One line builds a model: `caterva compose "Michaelis-Menten with a competitive inhibitor" --subject 1.1.1.27 --organism human --substrate pyruvate --inhibitor gossypol`. The sliders on this page drive a Michaelis-Menten demo computed in your browser.',
  },
  {
    id: "domains",
    q: "What does it cover?",
    a: "Enzymes. Michaelis-Menten kinetics, plain and inhibited, and mechanisms composed from a library of motifs, with constants from BRENDA; exact Gillespie SSA; and, on the main branch, structure audit, GROMACS setup with replicas, trajectory analysis and binding free energies. Epidemiology, population genetics, PCR and the oscillators were moved to archive/legacy_domains on 2026-09-27; the v0.4.0 release still runs them.",
  },
  {
    id: "pricing",
    q: "How much does it cost?",
    a: "Nothing. Caterva is free, open-source software (Apache-2.0) that runs on your own machine. There is no account and no paid plan.",
  },
  {
    id: "data-sources",
    q: "Where do the parameters come from?",
    a: "Kinetic constants come from BRENDA, each with its reference, organism and assay conditions, and when BRENDA holds several values for one constant the report shows how far they spread. PubMed and CORE supply papers to read when BRENDA has nothing, never a value. KEGG support is off by default pending a licence, and supplies substrate names rather than values. Numbers you choose, such as concentrations, are labelled as chosen.",
  },
  {
    id: "self-host",
    q: "Can I run Caterva on my own infrastructure?",
    a: "Yes. The command-line tools run on your own machine and need nothing else. The agent on this page needs the API server in the repository (Science-Agent-Pipeline/artifacts/api-server); where that server is not running, the agent says so rather than answering.",
  },
  {
    id: "compare",
    q: "How does this compare to other simulation tools?",
    a: "General-purpose tools such as COPASI and Tellurium simulate whatever constants you give them; finding those constants is left to you. Caterva looks them up in BRENDA, cites each one and labels any it could not find, then exports SBML and Antimony so the model opens in those tools. It does not replace them: its models are built from a library of mechanism motifs rather than written freely.",
  },
];

export default function FAQSection() {
  return (
    <section
      className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-blue"
      id="faq"
    >
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-muted text-[11px] font-mono font-medium">
            FAQ
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-muted/20 to-transparent" />
        </div>
        <h2 className="section-header">Frequently asked questions</h2>
        <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2 max-w-sm">
          What it is, what it costs, and what it does not do.
        </p>

        <TerminalWindow path="~ — faq" glow>
          <div className="mb-4 text-fg/92">
            <span className="text-signal">#</span> frequently asked
          </div>
          <Accordion
            type="single"
            collapsible
            className="divide-y divide-fg/[0.04]"
          >
            {FAQS.map((faq, i) => (
              <AccordionItem key={faq.id} value={faq.id} className="py-1">
                <AccordionTrigger className="faq-trigger group">
                  <span className="flex items-center gap-3">
                    <span className="text-[10px] text-fg/66 font-mono tabular-nums w-5 text-right shrink-0">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span>{faq.q}</span>
                  </span>
                  <svg
                    className="faq-chevron w-4 h-4 shrink-0"
                    viewBox="0 0 12 12"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M3 4.5L6 7.5L9 4.5"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </AccordionTrigger>
                <AccordionContent className="faq-content">
                  <div className="pl-8 pr-2 text-[12px] leading-relaxed">
                    {faq.a}
                  </div>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
