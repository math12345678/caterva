import { CAPABILITY_COUNT, GUARD_COUNT } from "@/lib/domains";
import { useEffect, useState, useRef } from "react";
import { motion } from "framer-motion";
import Reveal from "./Reveal";
import TerminalWindow from "./TerminalWindow";
import { totals } from "@/lib/testResults";

interface CounterProps {
  target: number;
  suffix?: string;
  label: string;
  delay?: number;
}

function AnimatedMetric({
  target,
  suffix = "",
  label,
  delay = 0,
}: CounterProps) {
  const [count, setCount] = useState(0);
  const [inView, setInView] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { threshold: 0.3 },
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!inView) return;
    const duration = 1200;
    const steps = 30;
    const increment = target / steps;
    let current = 0;
    const timer = setTimeout(() => {
      const interval = setInterval(() => {
        current += increment;
        if (current >= target) {
          setCount(target);
          clearInterval(interval);
        } else {
          setCount(Math.round(current));
        }
      }, duration / steps);
      return () => clearInterval(interval);
    }, delay);
    return () => clearTimeout(timer);
  }, [inView, target, delay]);

  return (
    <div
      ref={ref}
      className="metric-card text-center p-4 rounded-xl border border-fg/[0.08] bg-fg/[0.01] hover:border-signal/15 transition-all duration-500 hover:bg-signal/[0.02]"
    >
      <div className="text-[28px] md:text-[36px] font-mono font-medium text-signal tabular-nums count-reveal">
        {count.toLocaleString()}
        {suffix}
      </div>
      <div className="text-[11px] text-fg/70 mt-1">{label}</div>
    </div>
  );
}

// What each source is used for, as the code uses it (2026-09-29). PubMed
// was listed as "Literature citations" beside BRENDA, as if both supplied
// values; it supplies papers to read, never a number. KEGG was listed
// although no query reaches it by default; it is mentioned in the sources
// panel's footnote with the reason.
const TRUST_SOURCES = [
  {
    name: "BRENDA",
    desc: "Km, kcat and Ki, with references",
    url: "https://www.brenda-enzymes.org",
  },
  {
    name: "PubMed",
    desc: "Papers to read, never a value",
    url: "https://pubmed.ncbi.nlm.nih.gov",
  },
  {
    name: "roadrunner",
    desc: "High-performance SBML solver",
    url: "https://github.com/sys-bio/roadrunner",
  },
  {
    name: "GROMACS",
    desc: "Molecular dynamics engine",
    url: "https://www.gromacs.org",
  },
];

export default function TrustSection() {
  return (
    <section
      className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-amber"
      id="trust"
    >
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-caution text-[11px] font-mono font-medium">
            TRUST
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-caution/20 to-transparent" />
        </div>
        <h2 className="section-header">What is checked, and what is not</h2>
        <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2 max-w-md">
          Every literature constant names its source, and a number nobody
          measured says so. The solvers are checked against exact answers;
          the models are not validated against experiment.
        </p>

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
          <AnimatedMetric
            target={totals().passed}
            label="tests passing"
            delay={0}
          />
          <AnimatedMetric
            target={CAPABILITY_COUNT}
            label="capabilities built"
            delay={200}
          />
          <AnimatedMetric target={4} label="export formats" delay={400} />
          <AnimatedMetric
            target={GUARD_COUNT}
            label="correctness guards"
            delay={600}
          />
        </div>

        {/* Trust Badges */}
        <div className="flex flex-wrap gap-2 mb-8">
          {TRUST_SOURCES.map((src) => (
            <a
              key={src.name}
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              className="trust-badge"
              aria-label={`${src.name}: ${src.desc}`}
            >
              <span className="text-signal font-medium">{src.name}</span>
              <span className="text-fg/66 hidden sm:inline">{src.desc}</span>
              <svg
                className="w-3 h-3 text-fg/66"
                viewBox="0 0 12 12"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M4 2h6v6M10 2L2 10"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </a>
          ))}
        </div>

        {/* Pipeline Verification */}
        <TerminalWindow path="~ — checks" glow>
          <div className="mb-4 text-[11px] font-mono text-fg/60">
            # what every run is checked against
          </div>

          <div className="space-y-0">
            {[
              {
                step: "01",
                title: "Literature Resolution",
                desc: "Each constant is looked up in BRENDA under the compound it belongs to. One that is found names its reference; one that is not says why.",
                icon: "\u2318",
              },
              {
                step: "02",
                title: "Parameter Validation",
                desc: "Units, organism, isoform, inhibition mode and assay conditions are compared with the model. A mismatch is printed beside the value, never silently accepted.",
                icon: "\u2713",
              },
              {
                step: "03",
                title: "ODE Integration",
                desc: "Caterva + libRoadRunner solve the system, and conserved quantities are checked against the analytic invariant. Tolerances are per-domain, tightest on the closed-form cases.",
                icon: "\u26A1",
              },
              {
                step: "04",
                title: "Provenance Output",
                desc: "The report and all four exports carry each value's citation, conditions, source row and spread. A placeholder is marked in every one.",
                icon: "\u2261",
              },
            ].map((item) => (
              <div
                key={item.step}
                className="flex gap-4 py-3 group border-b border-fg/[0.06] last:border-0"
              >
                <div className="shrink-0 w-8 h-8 rounded-lg bg-fg/[0.03] border border-fg/[0.10] flex items-center justify-center text-[11px] text-fg/70 group-hover:text-signal group-hover:border-signal/20 transition-all duration-300">
                  {item.icon}
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[10px] text-fg/66 font-mono">
                      {item.step}
                    </span>
                    <span className="text-[13px] text-fg/78 font-medium group-hover:text-fg/92 transition-colors">
                      {item.title}
                    </span>
                  </div>
                  <p className="text-[11px] text-fg/76 leading-relaxed">
                    {item.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
