import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

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
  "get",
  "cite",
  "status",
  "waitlist",
] as const;

const LABELS: Record<string, string> = {
  how: "How it works",
  examples: "Examples",
  playground: "Playground",
  compare: "Compare",
  glossary: "Glossary",
  trust: "Trust",
  faq: "FAQ",
  domains: "Domains",
  tests: "Test suite",
  agent: "Agent",
  runs: "Recent runs",
  simulate: "Live simulator",
  exports: "Exports",
  roadmap: "Roadmap",
  team: "Team",
  get: "Get Caterva",
  cite: "Cite",
  status: "Sources",
  waitlist: "Updates",
};

export default function FloatingSectionCounter() {
  const [index, setIndex] = useState(-1);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Don't show until user has scrolled past the hero
    const checkScroll = () => {
      setVisible(window.scrollY > window.innerHeight * 0.6);
    };
    checkScroll();

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const idx = NAV_ITEMS.indexOf(
              entry.target.id as (typeof NAV_ITEMS)[number],
            );
            if (idx >= 0) setIndex(idx);
          }
        }
      },
      { threshold: 0.4, rootMargin: "-80px 0px 0px 0px" },
    );

    for (const item of NAV_ITEMS) {
      const el = document.getElementById(item);
      if (el) observer.observe(el);
    }

    window.addEventListener("scroll", checkScroll, { passive: true });
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", checkScroll);
    };
  }, []);

  const sectionId = index >= 0 ? NAV_ITEMS[index] : null;
  const label = sectionId ? (LABELS[sectionId] ?? sectionId) : null;

  return (
    <AnimatePresence>
      {visible && label && (
        <motion.div
          initial={{ opacity: 0, y: 12, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 12, scale: 0.9 }}
          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 hidden md:block"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-fg/[0.12] bg-surface/90 backdrop-blur-md px-3.5 py-1.5 shadow-lg shadow-surface/30">
            <motion.span
              key={index}
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-[10px] text-fg/70 font-mono tabular-nums"
            >
              {String(index + 1).padStart(2, "0")}
            </motion.span>
            <span className="w-px h-3 bg-fg/[0.06]" />
            <motion.span
              key={label}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              className="text-[10px] text-fg/76 font-mono uppercase tracking-wider"
            >
              {label}
            </motion.span>
            <span className="w-px h-3 bg-fg/[0.06]" />
            <span className="text-[10px] text-fg/66 font-mono">
              / {NAV_ITEMS.length}
            </span>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
