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
    id: "what-is-terrium",
    q: "What is Terrium?",
    a: 'Terrium is a scientific computing platform built for teaching labs. You describe a biological system in plain language — "lactate dehydrogenase with pyruvate" or "SIR outbreak with beta 0.3" — and Terrium resolves real kinetic parameters from BRENDA, KEGG, and PubMed, then runs a verified ODE simulation with full provenance. Every number traces back to a citation.',
  },
  {
    id: "how-accurate",
    q: "How accurate are the simulations?",
    a: "Every simulation is validated against closed-form solutions to 1e-10 tolerance in the Python test suite. Parameters are sourced exclusively from peer-reviewed literature — BRENDA for enzyme kinetics, KEGG for pathway data, and PubMed for supporting citations. We flag low-confidence values and never fabricate numbers. The RK4 integrator checks conserved quantities (population, mass) at every timestep.",
  },
  {
    id: "no-code",
    q: "Do I need to write code?",
    a: "No. You ask questions in plain English. The natural language agent resolves your query into structured parameters, validates them against known bounds, and runs the simulation. You can also fine-tune parameters via sliders, and the terminal shell supports commands like `simulate mm --km 2 --vmax 5`.",
  },
  {
    id: "domains",
    q: "What scientific domains are supported?",
    a: "Currently live: enzyme kinetics (Michaelis-Menten) and epidemiology (SIR/SEIR). Planned: PCR amplification, Monte Carlo simulation, population genetics, and molecular dynamics setup. We release domains only after the full test suite passes — 304+ tests and counting across the engine and literature layers.",
  },
  {
    id: "pricing",
    q: "How much does it cost?",
    a: "Terrium is pre-launch and currently free for pilot users. Join the waitlist and we'll reach out when spots open up — typically 1–2 weeks. We plan to offer free tiers for classrooms and researchers, with paid plans for high-throughput institutional use.",
  },
  {
    id: "data-sources",
    q: "Where do the parameters come from?",
    a: "Parameters are sourced from BRENDA (the world's most comprehensive enzyme database), KEGG (Kyoto Encyclopedia of Genes and Genomes), and PubMed. Every resolved value includes a citation trail — you can trace any number back to its source paper. No black-box AI hallucinations here.",
  },
  {
    id: "self-host",
    q: "Can I run Terrium on my own infrastructure?",
    a: "Yes. The Tellurium engine and literature layer are open-source and runnable locally. The landing page simulator even runs RK4 integration directly in your browser — no server required for basic exploration. The full pipeline (agent + SSE streaming) requires the API server.",
  },
  {
    id: "compare",
    q: "How does this compare to other simulation tools?",
    a: "Unlike general-purpose ODE tools (Copasi, Tellurium standalone), Terrium removes the parameter-hunting step. Unlike LLM-only science tools, every number is validated against real databases and closed-form solutions. The result: simulations you can cite in a lab report, not just interesting animations.",
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
          <span className="text-[#3B82F6] text-[11px] font-mono font-medium">
            FAQ
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#3B82F6]/20 to-transparent" />
        </div>
        <h2 className="section-header">Frequently asked questions</h2>
        <p className="font-sans text-[13px] text-white/30 mb-8 -mt-2 max-w-sm">
          Everything you need to know about verified scientific simulation.
        </p>

        <TerminalWindow path="~ — terrium faq" glow>
          <div className="mb-4 text-white/90">
            <span className="text-[#1D8A72]">$</span> terrium faq --all
          </div>
          <Accordion
            type="single"
            collapsible
            className="divide-y divide-white/[0.04]"
          >
            {FAQS.map((faq, i) => (
              <AccordionItem key={faq.id} value={faq.id} className="py-1">
                <AccordionTrigger className="faq-trigger group">
                  <span className="flex items-center gap-3">
                    <span className="text-[10px] text-white/15 font-mono tabular-nums w-5 text-right shrink-0">
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
