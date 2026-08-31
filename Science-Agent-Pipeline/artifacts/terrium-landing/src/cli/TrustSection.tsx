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
      className="metric-card text-center p-4 rounded-xl border border-white/[0.04] bg-white/[0.01] hover:border-[#1D8A72]/15 transition-all duration-500 hover:bg-[#1D8A72]/[0.02]"
    >
      <div className="text-[28px] md:text-[36px] font-mono font-medium text-[#1D8A72] tabular-nums count-reveal">
        {count.toLocaleString()}
        {suffix}
      </div>
      <div className="text-[11px] text-white/30 mt-1">{label}</div>
    </div>
  );
}

const TRUST_SOURCES = [
  {
    name: "BRENDA",
    desc: "Enzyme functional data",
    url: "https://www.brenda-enzymes.org",
  },
  {
    name: "KEGG",
    desc: "Pathway & genomic data",
    url: "https://www.genome.jp/kegg/",
  },
  {
    name: "PubMed",
    desc: "Literature citations",
    url: "https://pubmed.ncbi.nlm.nih.gov",
  },
  {
    name: "Terium",
    desc: "ODE simulation engine",
    url: "https://terium.analogmachine.org",
  },
  {
    name: "roadrunner",
    desc: "High-performance SBML solver",
    url: "https://github.com/sys-bio/roadrunner",
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
          <span className="text-[#F59E0B] text-[11px] font-mono font-medium">
            TRUST
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-[#F59E0B]/20 to-transparent" />
        </div>
        <h2 className="section-header">Built on real science</h2>
        <p className="font-sans text-[13px] text-white/30 mb-8 -mt-2 max-w-sm">
          Every number is traceable. Every simulation is verified. No black
          boxes.
        </p>

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
          <AnimatedMetric
            target={totals().passed}
            label="tests passing"
            delay={0}
          />
          <AnimatedMetric
            target={15}
            label="simulation domains"
            delay={200}
          />
          <AnimatedMetric target={3} label="literature sources" delay={400} />
          <AnimatedMetric
            target={72}
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
              <span className="text-[#1D8A72] font-medium">{src.name}</span>
              <span className="text-white/25 hidden sm:inline">{src.desc}</span>
              <svg
                className="w-3 h-3 text-white/15"
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
        <TerminalWindow path="~ — how we validate" glow>
          <div className="mb-4 text-white/90">
            <span className="text-[#1D8A72]">$</span> terrium validate
            --pipeline
          </div>

          <div className="space-y-0">
            {[
              {
                step: "01",
                title: "Literature Resolution",
                desc: "LLM + structured keyword matching against BRENDA, KEGG & PubMed. Every parameter gets a source citation.",
                icon: "\u2318",
              },
              {
                step: "02",
                title: "Parameter Validation",
                desc: "Cross-checked against known plausibility bounds. Flagged values are surfaced with warnings — never silently accepted.",
                icon: "\u2713",
              },
              {
                step: "03",
                title: "ODE Integration",
                desc: "Terium + libRoadRunner solve the system, and conserved quantities are checked against the analytic invariant. Tolerances are per-domain, tightest on the closed-form cases.",
                icon: "\u26A1",
              },
              {
                step: "04",
                title: "Provenance Output",
                desc: "Full reasoning trail, citation list, parameter flags, and trajectory exported with every run.",
                icon: "\u2261",
              },
            ].map((item) => (
              <div
                key={item.step}
                className="flex gap-4 py-3 group border-b border-white/[0.03] last:border-0"
              >
                <div className="shrink-0 w-8 h-8 rounded-lg bg-white/[0.03] border border-white/[0.05] flex items-center justify-center text-[11px] text-white/30 group-hover:text-[#1D8A72] group-hover:border-[#1D8A72]/20 transition-all duration-300">
                  {item.icon}
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[10px] text-white/15 font-mono">
                      {item.step}
                    </span>
                    <span className="text-[13px] text-white/70 font-medium group-hover:text-white/90 transition-colors">
                      {item.title}
                    </span>
                  </div>
                  <p className="text-[11px] text-white/35 leading-relaxed">
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
