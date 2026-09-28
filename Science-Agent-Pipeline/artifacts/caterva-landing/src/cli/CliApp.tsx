import MuleChapters from "@/mule/MuleChapters";
import { Lockup, Mark } from "@/components/brand/Mark";
import { useState, useEffect, useRef, lazy, Suspense } from "react";
import {
  motion,
  AnimatePresence,
  useScroll,
  useTransform,
  useSpring,
} from "framer-motion";
import TerminalWindow from "./TerminalWindow";
import TestPanelBody from "./TestPanel";
import AgentSimulator from "./AgentSimulator";
import RecentRuns from "./RecentRuns";
import SimulatorPanel, { type Domain } from "./SimulatorPanel";
import InteractiveShell from "./InteractiveShell";
import PipelineFlow from "./PipelineFlow";
import StatsBar from "./StatsBar";
import TypedLine from "./TypedLine";
import CommandPalette from "./CommandPalette";
import Reveal from "./Reveal";
import ScrollProgress from "./ScrollProgress";
import FeatureCards from "./FeatureCards";
import DashboardPreview from "./DashboardPreview";
import ExampleGallery from "./ExampleGallery";
import StaggeredHero from "./StaggeredHero";
import MetricsBar from "./MetricsBar";
import PlaygroundTabs from "./PlaygroundTabs";
import WorkflowCompare from "./WorkflowCompare";
import ExportFormats from "./ExportFormats";
import GlossarySection from "./GlossarySection";
import ChangelogModal from "./ChangelogModal";
import FloatingSectionCounter from "./FloatingSectionCounter";
import LiveStatusPanel from "./LiveStatusPanel";
import CookieConsent from "./CookieConsent";
import StickyCTA from "./StickyCTA";
import MobileBottomNav from "./MobileBottomNav";
import Magnetic from "@/components/ui/Magnetic";
import BackendHealth from "@/components/ui/backend-health";
import ShortcutHelp from "@/components/ui/shortcut-help";
import BackToTop from "@/components/ui/back-to-top";
import { WaitlistForm } from "@/components/ui/WaitlistForm";
import FooterMetrics from "@/components/ui/footer-metrics";
import WaitlistCounter from "@/components/ui/waitlist-counter";
import { totals } from "@/lib/testResults";

const FAQSection = lazy(() => import("./FAQSection"));
const TrustSection = lazy(() => import("./TrustSection"));
const PricingPlans = lazy(() => import("./PricingPlans"));
const HowToCiteSection = lazy(() => import("./HowToCiteSection"));
const RoadmapSection = lazy(() => import("./RoadmapSection"));
const TeamSection = lazy(() => import("./TeamSection"));

function LazyFallback({ rows = 4 }: { rows?: number }) {
  return (
    <section className="max-w-3xl mx-auto px-4 md:px-6 py-10">
      <div className="space-y-6">
        {/* Label skeleton */}
        <div className="flex items-center gap-3">
          <div className="h-3 w-16 bg-fg/[0.03] rounded animate-pulse" />
          <div className="h-px flex-1 bg-gradient-to-r from-fg/[0.04] to-transparent" />
        </div>
        {/* Header skeleton */}
        <div className="h-8 w-48 bg-fg/[0.03] rounded animate-pulse mb-2" />
        {/* Content rows */}
        <div className="space-y-3">
          {Array.from({ length: rows }).map((_, i) => (
            <div
              key={i}
              className="h-16 bg-fg/[0.015] rounded-xl border border-fg/[0.06] animate-pulse"
              style={{ animationDelay: `${i * 100}ms` }}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

const NAV_ITEMS = [
  "system",
  "microscope",
  "examples",
  "playground",
  "compare",
  "glossary",
  "trust",
  "faq",
  "domains",
  "tests",
  "agent",
  "runs",
  "simulate",
  "exports",
  "roadmap",
  "team",
  "pricing",
  "cite",
  "status",
  "waitlist",
] as const;

// The header carries the few sections a first-time visitor needs; the side
// dots and the command palette (⌘K) still reach every section.
const HEADER_NAV = ["system", "microscope", "playground", "agent", "domains", "cite", "waitlist"] as const;
const HEADER_LABEL: Partial<Record<(typeof HEADER_NAV)[number], string>> = {
  system: "watch a run",
  microscope: "evidence",
};

import { DOMAINS } from "@/lib/domains";

function Section({
  children,
  className = "",
  id,
}: {
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section
      id={id}
      className={`scroll-mt-16 max-w-3xl mx-auto px-4 md:px-6 py-10 ${className}`}
    >
      {children}
    </section>
  );
}

function scrollToSection(id: string) {
  document
    .getElementById(id)
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function SectionNav() {
  const [active, setActive] = useState("");
  const [visited, setVisited] = useState<Set<string>>(new Set());

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActive(entry.target.id);
            setVisited((prev) => new Set([...prev, entry.target.id]));
          }
        }
      },
      { threshold: 0.3, rootMargin: "-80px 0px 0px 0px" },
    );
    for (const item of NAV_ITEMS) {
      const el = document.getElementById(item);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  return (
    <nav className="fixed right-4 top-1/2 -translate-y-1/2 z-30 hidden md:flex flex-col gap-3">
      {NAV_ITEMS.map((item) => {
        const isActive = active === item;
        const isVisited = visited.has(item);
        return (
          <a
            key={item}
            href={`#${item}`}
            className={`block w-2 h-2 rounded-full transition-all duration-500 ${
              isActive
                ? "bg-signal scale-125"
                : isVisited
                  ? "bg-fg/25 hover:bg-fg/40"
                  : "bg-fg/10 hover:bg-fg/25"
            }`}
            aria-label={item}
          />
        );
      })}
    </nav>
  );
}

function ParallaxHero({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 100,
    damping: 30,
  });
  const y = useTransform(smoothProgress, [0, 1], [0, 120]);
  const opacity = useTransform(smoothProgress, [0, 0.7], [1, 0.3]);

  return (
    <section
      ref={ref}
      className="relative pt-28 pb-20 overflow-hidden min-h-screen flex items-center dot-grid-bg"
    >
      <motion.div style={{ y, opacity }} className="relative z-10 w-full">
        {children}
      </motion.div>
    </section>
  );
}


export default function CliApp() {
  const [simDomain, setSimDomain] = useState<Domain>("mm");
  const [rerunQuery, setRerunQuery] = useState<string>("");
  const [mobileMenu, setMobileMenu] = useState(false);
  const [changelogOpen, setChangelogOpen] = useState(false);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "j" || e.key === "ArrowDown") {
        const tag = (e.target as HTMLElement)?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return;
        e.preventDefault();
        const current = NAV_ITEMS.findIndex((id) => {
          const el = document.getElementById(id);
          if (!el) return false;
          const rect = el.getBoundingClientRect();
          return rect.top > 80;
        });
        const next =
          current >= 0
            ? NAV_ITEMS[Math.min(current, NAV_ITEMS.length - 1)]
            : NAV_ITEMS[0];
        if (next)
          document
            .getElementById(next)
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      if (e.key === "k" || e.key === "ArrowUp") {
        const tag = (e.target as HTMLElement)?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return;
        e.preventDefault();
        const reversed = [...NAV_ITEMS].reverse();
        const current = reversed.findIndex((id) => {
          const el = document.getElementById(id);
          if (!el) return false;
          const rect = el.getBoundingClientRect();
          return rect.top < -40;
        });
        const prev =
          current >= 0
            ? reversed[Math.min(current, NAV_ITEMS.length - 1)]
            : NAV_ITEMS[NAV_ITEMS.length - 1];
        if (prev)
          document
            .getElementById(prev)
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  return (
    <div
      className="min-h-screen bg-surface text-fg/92 font-sans selection:bg-signal/30"
      id="top"
    >
      <a
        href="#system"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[9999] focus:px-4 focus:py-2 focus:rounded-lg focus:border focus:border-signal/40 focus:bg-surface focus:text-signal focus:text-[13px] focus:font-medium focus:shadow-lg"
      >
        Skip to main content
      </a>
      <ScrollProgress />
      <FloatingSectionCounter />
      <SectionNav />
      <ShortcutHelp />
      <BackToTop />
      <CommandPalette onNavigate={scrollToSection} onQuery={setRerunQuery} />
      <ChangelogModal
        open={changelogOpen}
        onClose={() => setChangelogOpen(false)}
      />
      <MobileBottomNav />
      <header
        className="sticky top-0 z-20 border-b border-fg/[0.06] bg-surface/80 backdrop-blur-xl"
        role="banner"
        aria-label="Site header"
      >
        <div className="max-w-3xl mx-auto px-4 md:px-6 h-12 flex items-center justify-between text-[12px]">
          <div className="flex items-center gap-4">
            <Magnetic strength={0.08}>
              <a href="#" className="text-fg flex items-center" aria-label="caterva, back to top">
                <Lockup size={22} />
              </a>
            </Magnetic>
            <BackendHealth />
          </div>

          <nav className="hidden md:flex items-center gap-1" aria-label="Main sections">
            {HEADER_NAV.map((item) => (
              <Magnetic key={item} strength={0.06}>
                <a
                  href={`#${item}`}
                  className="px-2.5 py-1 rounded-md text-fg/76 hover:text-fg hover:bg-fg/[0.05] transition-colors duration-200 text-[13px] whitespace-nowrap"
                >
                  {HEADER_LABEL[item] ?? item}
                </a>
              </Magnetic>
            ))}
            <span className="ml-2 text-[10px] text-fg/66 hidden lg:inline">
              <kbd className="px-1 py-0.5 rounded border border-fg/[0.12] text-fg/66">
                {"\u2318K"}
              </kbd>
            </span>
          </nav>

          <button
            onClick={() => setMobileMenu(!mobileMenu)}
            className="md:hidden flex flex-col gap-1 p-3.5 -m-1.5 text-fg/70 hover:text-fg/78 transition-colors"
            aria-label={mobileMenu ? "Close menu" : "Open menu"}
            aria-expanded={mobileMenu}
          >
            <span
              className={`block w-4 h-px bg-current transition-transform duration-300 ${mobileMenu ? "rotate-45 translate-y-[3px]" : ""}`}
            />
            <span
              className={`block w-4 h-px bg-current transition-opacity duration-300 ${mobileMenu ? "opacity-0" : ""}`}
            />
            <span
              className={`block w-4 h-px bg-current transition-transform duration-300 ${mobileMenu ? "-rotate-45 -translate-y-[3px]" : ""}`}
            />
          </button>
        </div>

        <AnimatePresence>
          {mobileMenu && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="md:hidden border-t border-fg/[0.06] bg-surface/95 backdrop-blur-xl overflow-hidden"
            >
              <div className="px-4 py-3 space-y-2">
                {NAV_ITEMS.map((item) => (
                  <a
                    key={item}
                    href={`#${item}`}
                    onClick={() => setMobileMenu(false)}
                    className="block text-[12px] text-fg/70 hover:text-fg/85 transition-colors py-1.5 uppercase tracking-wide"
                  >
                    {item}
                  </a>
                ))}
                <div className="text-[10px] text-fg/66 pt-2 border-t border-fg/[0.06]">
                  Press{" "}
                  <kbd className="px-1 rounded border border-fg/[0.12]">
                    {"\u2318K"}
                  </kbd>{" "}
                  for quick navigation
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </header>
      {/* ─── HERO ─── */}
      <ParallaxHero>
        <div className="max-w-3xl mx-auto px-4 md:px-6">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="inline-flex items-center gap-2 rounded-full border border-signal/20 bg-signal/[0.04] px-3 py-1 text-[11px] text-fg/76 mb-10"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-caution animate-pulse" />
            <span className="text-caution/70">pre-launch</span> &middot;
            <button
              onClick={() => setChangelogOpen(true)}
              className="bg-transparent border-none p-0 text-fg/70 hover:text-signal transition-colors cursor-pointer font-sans text-[11px]"
            >
              what&apos;s new
            </button>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-10 mb-12">
            <div className="md:col-span-3">
              <motion.h1
                initial={{ opacity: 1 }}
                animate={{ opacity: 1 }}
                className="hero-heading text-[46px] md:text-[64px] mb-7"
              >
                <StaggeredHero
                  lines={[
                    {
                      text: "Ask a question.",
                      className: "text-fg hero-heading-strong",
                      delayOffset: 0.1,
                    },
                    {
                      text: "Get a verified",
                      className: "text-fg/80 hero-heading-strong",
                      delayOffset: 0.45,
                    },
                    {
                      text: "simulation.",
                      className: "text-fg/70 hero-heading-strong",
                      delayOffset: 0.75,
                    },
                  ]}
                />
              </motion.h1>

              <motion.p
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.3 }}
                className="font-sans text-[15px] md:text-[17px] text-fg/70 max-w-md mb-8 leading-relaxed"
              >
                Enzyme kinetics and molecular dynamics for research groups and
                teaching labs. Real constants from the literature, audited
                structures, simulations that say whether they converged. Every
                number traceable to its citation.
              </motion.p>

              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.5 }}
                className="mb-5 text-[12px] text-fg/66"
              >
                <TypedLine
                  command="caterva agent --simulate 'lactate dehydrogenase with pyruvate'"
                  delayMs={500}
                  speedMs={18}
                />
              </motion.div>

              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6, delay: 0.75 }}
                className="flex flex-wrap items-center gap-5 text-[11px] mb-4"
              >
                <a
                  href="#system"
                  className="inline-flex items-center gap-2 rounded-lg bg-ink px-5 py-2.5 text-[13px] text-paper font-medium transition-colors duration-200 hover:bg-signal-deep"
                >
                  watch a run be built
                  <svg className="w-3.5 h-3.5" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                    <path d="M6 2v7M2 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </a>
                <a
                  href="#agent"
                  className="inline-flex items-center gap-2 rounded-lg border border-signal/30 bg-signal/[0.06] px-5 py-2.5 text-[13px] text-signal font-medium transition-colors duration-200 hover:bg-signal/[0.10]"
                >
                  try the agent
                  <svg className="w-3.5 h-3.5" viewBox="0 0 12 12" fill="none">
                    <path
                      d="M2 6h7M6 2l4 4-4 4"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </a>
                <span className="text-fg/66 hidden sm:inline">
                  <kbd className="px-1.5 rounded border border-fg/[0.12] text-fg/66">
                    {"\u2318K"}
                  </kbd>{" "}
                  navigate
                </span>
              </motion.div>
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.9 }}
              >
                <MetricsBar />
              </motion.div>
            </div>

            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{
                duration: 0.8,
                delay: 0.6,
                ease: [0.16, 1, 0.3, 1],
              }}
              className="md:col-span-2 md:pt-2"
            >
              <DashboardPreview />
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.5 }}
            className="flex justify-center mt-20"
          >
            <div className="flex flex-col items-center gap-1 text-fg/66 text-[9px] uppercase tracking-widest">
              <span>scroll</span>
              <motion.div
                animate={{ y: [0, 6, 0] }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
                className="w-px h-6 bg-gradient-to-b from-fg/30 to-transparent"
              />
            </div>
          </motion.div>
        </div>
      </ParallaxHero>
      <div className="section-divider" />
      {/* THE RUN: the MuleRun chapters, merged (Evidence Cathedral, system
          atlas, orchestration console, evidence rail, microscope, trust
          layer, runtimes). One full-width ink chapter on the paper page. */}
      <MuleChapters />
      {/* EXAMPLES */}
      <Section id="examples" className="pb-12 pt-8">
        <Reveal>
          <div className="flex items-center gap-4 mb-6">
            <span className="text-signal text-[11px] font-mono font-medium">
              00
            </span>
            <span className="h-px flex-1 bg-gradient-to-r from-signal/20 to-transparent" />
          </div>
          <h2 className="section-header">See it in action</h2>
          <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2">
            Pre-computed examples. No backend required.
          </p>
          <ExampleGallery onTryQuery={setRerunQuery} />
        </Reveal>
      </Section>
      {/* KINETICS PLAYGROUND */}
      <div className="section-divider-blue" />
      <PlaygroundTabs />
      {/* WORKFLOW COMPARISON */}
      <div className="section-divider-amber" />
      <WorkflowCompare />
      {/* TESTIMONIALS -- removed 2026-08-15. The carousel carried five
          invented quotes attributed to named academics at five real
          universities, under a "Trusted by educators" heading, for a
          pre-launch product with a waitlist and no users. The institutions
          are listed in docs/ENDORSEMENTS.md and the reasoning in ADR 0071;
          they are deliberately not repeated here, because restating a
          false claim in order to explain its removal still puts the claim
          in the page.

          Do not restore this section with placeholder quotes. If real
          endorsements are obtained, record them in docs/ENDORSEMENTS.md
          with the permission behind each one --
          scripts/check_no_fabricated_endorsements.py fails when a public
          page names an institution without a matching record. */}
      {/* GLOSSARY */}
      <div className="section-divider-blue" />
      <GlossarySection />
      {/* FEATURES */}
      <FeatureCards />
      <div className="section-divider" />
      {/* TRUST / SOCIAL PROOF */}
      <Suspense fallback={<LazyFallback />}>
        <TrustSection />
      </Suspense>
      <div className="section-divider-purple" />
      {/* FAQ */}
      <Suspense fallback={<LazyFallback />}>
        <FAQSection />
      </Suspense>
      <div className="section-divider" />
      {/* DOMAINS */}
      <Section id="domains" className="section-bg-teal pb-16 pt-12">
        <Reveal>
          <div className="flex items-center gap-4 mb-6">
            <span className="text-signal text-[11px] font-mono font-medium">
              01
            </span>
            <span className="h-px flex-1 bg-gradient-to-r from-signal/20 to-transparent" />
          </div>
          <h2 className="section-header">Supported domains</h2>
          <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2">
            Enzyme kinetics, exact stochastic kinetics, and the structure
            and molecular-dynamics tools that sit beside them.
          </p>
          <TerminalWindow path="~ &mdash; caterva domains --list" glow>
            <div className="mb-4 text-fg/92">
              <span className="text-signal">$</span> caterva domains --list
            </div>
            <div className="space-y-2">
              {DOMAINS.map((d, i) => (
                <motion.div
                  key={d.id}
                  initial={{ opacity: 0, x: -8 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: i * 0.05 }}
                  className="flex items-start gap-3 text-[12px] group"
                >
                  <span
                    className={`mt-0.5 shrink-0 rounded-md px-1.5 py-0.5 text-[10px] uppercase tracking-wide transition-all ${
                      d.status === "live"
                        ? "bg-signal/15 text-signal group-hover:bg-signal/20"
                        : "bg-fg/5 text-fg/70 group-hover:bg-fg/[0.08]"
                    }`}
                  >
                    {d.status}
                  </span>
                  <div>
                    <span className="text-fg/85 group-hover:text-fg transition-colors">
                      {d.id}
                    </span>
                    <span className="text-fg/70"> &mdash; {d.desc}</span>
                  </div>
                </motion.div>
              ))}
            </div>
          </TerminalWindow>
        </Reveal>
      </Section>
      <div className="section-divider-blue" />
      {/* TESTS */}
      <Section id="tests" className="section-bg-blue pb-16 pt-12">
        <Reveal>
          <div className="flex items-center gap-4 mb-6">
            <span className="text-muted text-[11px] font-mono font-medium">
              02
            </span>
            <span className="h-px flex-1 bg-gradient-to-r from-muted/20 to-transparent" />
          </div>
          <h2 className="section-header">Test suite</h2>
          <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2">
            {totals().passed.toLocaleString()} tests across the full stack
            — zero failures.
          </p>
          <TerminalWindow path="~ &mdash; caterva test --run --no-skip -v" glow>
            <TestPanelBody />
          </TerminalWindow>
        </Reveal>
      </Section>
      <div className="section-divider-amber" />
      {/* AGENT */}
      <Section id="agent" className="section-bg-amber pb-16 pt-12">
        <Reveal>
          <div className="flex items-center gap-4 mb-6">
            <span className="text-caution text-[11px] font-mono font-medium">
              03
            </span>
            <span className="h-px flex-1 bg-gradient-to-r from-caution/20 to-transparent" />
          </div>
          <h2 className="section-header">Try the agent</h2>
          <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2">
            Describe your experiment. We handle the rest.
          </p>
          <AgentSimulator
            key={rerunQuery}
            rerunQuery={rerunQuery}
            onRerunConsumed={() => setRerunQuery("")}
          />
        </Reveal>
      </Section>
      <div className="section-divider-purple" />
      {/* RUNS */}
      <Section id="runs" className="section-bg-purple pb-16 pt-12">
        <Reveal>
          <div className="flex items-center gap-4 mb-6">
            <span className="text-muted text-[11px] font-mono font-medium">
              04
            </span>
            <span className="h-px flex-1 bg-gradient-to-r from-muted/20 to-transparent" />
          </div>
          <h2 className="section-header">Recent runs</h2>
          <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2">
            Your past simulations, ready to re-run or export.
          </p>
          <RecentRuns onReRun={setRerunQuery} />
        </Reveal>
      </Section>
      <div className="section-divider" />
      {/* SIMULATE */}
      <Section id="simulate" className="section-bg-teal pb-16 pt-12">
        <Reveal>
          <div className="flex items-center gap-4 mb-6">
            <span className="text-signal text-[11px] font-mono font-medium">
              05
            </span>
            <span className="h-px flex-1 bg-gradient-to-r from-signal/20 to-transparent" />
          </div>
          <h2 className="section-header">Live simulator</h2>
          <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2">
            Browser-side ODE solver. Tune parameters in real time.
          </p>
          <SimulatorPanel domain={simDomain} onDomainChange={setSimDomain} />
        </Reveal>
      </Section>
      <div className="section-divider-purple" />
      {/* EXPORT FORMATS */}
      <ExportFormats />
      <div className="section-divider" />
      {/* ROADMAP */}
      <Suspense fallback={<LazyFallback />}>
        <RoadmapSection />
      </Suspense>
      <div className="section-divider-blue" />
      {/* TEAM */}
      <Suspense fallback={<LazyFallback />}>
        <TeamSection />
      </Suspense>
      <div className="section-divider-purple" />
      {/* PRICING */}
      <Suspense fallback={<LazyFallback />}>
        <PricingPlans />
      </Suspense>
      <div className="section-divider-blue" />
      {/* HOW TO CITE */}
      <Suspense fallback={<LazyFallback />}>
        <HowToCiteSection />
      </Suspense>
      <div className="section-divider-amber" />
      {/* WAITLIST */}
      <Section id="waitlist" className="section-bg-amber-strong pb-24 pt-16">
        <Reveal>
          <div className="flex items-center gap-4 mb-6">
            <span className="text-caution text-[11px] font-mono font-medium">
              06
            </span>
            <span className="h-px flex-1 bg-gradient-to-r from-caution/20 to-transparent" />
          </div>
          <h2 className="section-header">Join the waitlist</h2>
          <TerminalWindow path="~ &mdash; caterva waitlist --join" glow>
            <div className="mb-4 text-fg/92">
              <span className="text-signal">$</span> caterva waitlist --join
            </div>
            <p className="text-fg/70 text-[13px] mb-6 leading-relaxed">
              Caterva is pre-launch. Join the waitlist and we&apos;ll reach out
              when a pilot spot opens up.
            </p>
            <div className="mb-4">
              <WaitlistCounter />
            </div>
            <WaitlistForm />
          </TerminalWindow>
        </Reveal>
      </Section>
      <div className="section-divider-amber" />
      {/* SYSTEM STATUS */}
      <LiveStatusPanel />
      <div className="section-divider" />
      <footer
        className="border-t border-fg/[0.06] py-16"
        role="contentinfo"
        aria-label="Site footer"
      >
        <div className="max-w-3xl mx-auto px-4 md:px-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4 text-[11px] text-fg/66">
            <div className="flex items-center gap-3">
              <Mark size={16} className="text-fg" />
              <span>
                enzyme kinetics and molecular dynamics, every number cited
              </span>
            </div>
            <div className="flex items-center gap-4">
              <button
                onClick={() => setChangelogOpen(true)}
                className="text-fg/66 hover:text-fg/76 transition-colors"
              >
                changelog
              </button>
              <a
                href="#cite"
                className="text-fg/66 hover:text-fg/76 transition-colors"
              >
                cite
              </a>
              <a
                href="#pricing"
                className="text-fg/66 hover:text-fg/76 transition-colors"
              >
                pricing
              </a>
              <span className="flex items-center gap-1.5">
                <span className="text-signal">exit</span>
                <motion.span
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 2, repeat: Infinity }}
                  className="text-signal/60"
                >
                  0
                </motion.span>
              </span>
            </div>
          </div>
          <div className="mt-4 flex flex-col md:flex-row items-center justify-between gap-1 text-[10px] text-fg/66">
            <span>Built by Smyan Reddy and team &middot; Pre-launch</span>
            <FooterMetrics />
          </div>
        </div>
      </footer>
      <CookieConsent />
      <StickyCTA />
      <div className="md:hidden h-16" /> {/* spacer for mobile bottom nav */}
    </div>
  );
}
