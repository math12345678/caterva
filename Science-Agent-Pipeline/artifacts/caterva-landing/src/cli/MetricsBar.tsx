import { CAPABILITY_COUNT, DATA_SOURCES, GUARD_COUNT } from "@/lib/domains";
import { useEffect, useState, useRef } from "react";
import { motion } from "framer-motion";
import AnimatedCounter from "@/components/ui/animated-counter";
import { totals } from "@/lib/testResults";

interface MetricItem {
  key: string;
  target: number;
  suffix: string;
  label: string;
  color: string;
}

// "tests" reads from testResults.ts's own totals() rather than repeating
// the count as a second hardcoded literal -- two copies of the same fact
// is exactly how the count this replaced (304) went stale in the first
// place while testResults.ts had already moved on.
//
// "sources" was a literal 3 labelled "literature sources", left from when
// the page named BRENDA, KEGG and PubMed -- and KEGG is off by default. It
// now counts the sources docs/data-sources.json attributes, through the
// generated repoFacts.json, and says that is what it counts. "guards" is
// scripts/check_*.py from the same file.
const METRICS: MetricItem[] = [
  {
    key: "tests",
    target: totals().passed,
    suffix: "",
    label: "tests passing",
    color: "#5D7F8D",
  },
  {
    key: "domains",
    target: CAPABILITY_COUNT,
    suffix: "",
    label: "capabilities built",
    color: "#6A6E78",
  },
  {
    key: "sources",
    target: DATA_SOURCES.length,
    suffix: "",
    label: "attributed data sources",
    color: "#946522",
  },
  {
    key: "guards",
    target: GUARD_COUNT,
    suffix: "",
    label: "correctness guards",
    color: "#6A6E78",
  },
];

export default function MetricsBar({ className = "" }: { className?: string }) {
  const [inView, setInView] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { threshold: 0.3 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className={`flex flex-wrap items-center gap-4 ${className}`}>
      {METRICS.map((m, i) => (
        <motion.div
          key={m.key}
          initial={{ opacity: 0, y: 12 }}
          animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }}
          transition={{
            duration: 0.5,
            delay: i * 0.1,
            ease: [0.16, 1, 0.3, 1],
          }}
          className="flex items-center gap-2"
        >
          <span
            className="text-[15px] font-semibold tabular-nums font-mono"
            style={{ color: m.color }}
          >
            {inView ? (
              <AnimatedCounter
                target={m.target}
                suffix={m.suffix}
                duration={1800}
              />
            ) : (
              <span>0{m.suffix}</span>
            )}
          </span>
          <span className="text-[11px] text-fg/66">{m.label}</span>
        </motion.div>
      ))}
    </div>
  );
}
