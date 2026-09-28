import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import Reveal from "./Reveal";
import TerminalWindow from "./TerminalWindow";

const FAQS = [
  {
    id: "what-is-caterva",
    q: "What is Caterva?",
    a: 'Caterva is a scientific computing platform built for teaching labs. You describe a biological system in plain language — "lactate dehydrogenase with pyruvate" or "SIR outbreak with beta 0.3" — and Caterva resolves real kinetic parameters from BRENDA, with PubMed for supporting citations, then runs a verified ODE simulation with full provenance. Every number traces back to a citation.',
  },
  {
    id: "how-accurate",
    q: "How accurate are the simulations?",
    a: "Every domain is checked against something that is not the solver itself: an exact closed-form solution, an independent integrator (scipy's solve_ivp, which shares no code with roadrunner), or a physical invariant tested across the input space with Hypothesis. Tolerances vary by domain, from 1e-10 on the analytic cases to 1e-4 where a stochastic method makes anything tighter meaningless. Parameters are sourced exclusively from peer-reviewed literature — BRENDA for enzyme kinetics (Km, Ki, kcat) and PubMed for supporting citations. KEGG support is implemented but disabled by default: KEGG's terms require a licence for service providers and Caterva does not hold one, so no query reaches it unless an operator sets CATERVA_ENABLE_KEGG. Even enabled, it resolves substrate NAMES, never a kinetic value. We flag low-confidence values and never fabricate numbers. The RK4 integrator checks conserved quantities (population, mass) at every timestep.",
  },
  {
    id: "no-code",
    q: "Do I need to write code?",
    a: "No. You ask questions in plain English. The natural language agent resolves your query into structured parameters, validates them against known bounds, and runs the simulation. You can also fine-tune parameters via sliders, and the terminal shell supports commands like `simulate mm --km 2 --vmax 5`.",
  },
  {
    id: "domains",
    q: "What scientific domains are supported?",
    a: "Fifteen domains are built: enzyme kinetics (plain and competitively inhibited Michaelis-Menten), SIR/SEIR epidemiology, PCR amplification, Monte Carlo, population genetics (Wright-Fisher, one- and two-locus), Lennard-Jones molecular dynamics, Gillespie SSA (three variants), and three ODE oscillators — Lotka-Volterra, the Tyson cell-cycle model and the Elowitz-Leibler repressilator. We release a domain only after its suite passes; the counts in README.md are checked against the repository on every build by scripts/check_documented_counts.py.",
  },
  {
    id: "pricing",
    q: "How much does it cost?",
    a: "Caterva is pre-launch and currently free for pilot users. Join the waitlist and we'll reach out when spots open up — typically 1–2 weeks. We plan to offer free tiers for classrooms and researchers, with paid plans for high-throughput institutional use.",
  },
  {
    id: "data-sources",
    q: "Where do the parameters come from?",
    a: "Parameters are sourced from BRENDA (the world's most comprehensive enzyme database) and PubMed. KEGG is integrated but off by default pending a licence, and supplies substrate names rather than parameter values. Every resolved value includes a citation trail — you can trace any number back to its source paper. No black-box AI hallucinations here.",
  },
  {
    id: "self-host",
    q: "Can I run Caterva on my own infrastructure?",
    a: "Not yet — the repository isn't public. The engine and literature layer are built to run locally and will ship Apache-2.0 licensed once it is; join the waitlist to hear when. In the meantime, the landing page simulator runs RK4 integration directly in your browser — no server required for basic exploration. The full pipeline (agent + SSE streaming) requires the API server.",
  },
  {
    id: "compare",
    q: "How does this compare to other simulation tools?",
    a: "Unlike general-purpose ODE tools (Copasi, Caterva standalone), Caterva removes the parameter-hunting step. Unlike LLM-only science tools, every number is validated against real databases and closed-form solutions. The result: simulations you can cite in a lab report, not just interesting animations.",
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
          Everything you need to know about verified scientific simulation.
        </p>

        <TerminalWindow path="~ — caterva faq" glow>
          <div className="mb-4 text-fg/92">
            <span className="text-signal">$</span> caterva faq --all
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
