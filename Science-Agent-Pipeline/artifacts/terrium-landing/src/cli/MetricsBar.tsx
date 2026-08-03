import { useEffect, useState, useRef } from "react";
import { motion } from "framer-motion";
import AnimatedCounter from "@/components/ui/animated-counter";

interface MetricItem {
  key: string;
  target: number;
  suffix: string;
  label: string;
  color: string;
}

const METRICS: MetricItem[] = [
  {
    key: "tests",
    target: 304,
    suffix: "+",
    label: "tests passing",
    color: "#1D8A72",
  },
  {
    key: "domains",
    target: 6,
    suffix: "",
    label: "simulation domains",
    color: "#3B82F6",
  },
  {
    key: "sources",
    target: 3,
    suffix: "",
    label: "literature sources",
    color: "#F59E0B",
  },
  {
    key: "opensource",
    target: 100,
    suffix: "%",
    label: "open source",
    color: "#8B5CF6",
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
          <span className="text-[11px] text-white/25">{m.label}</span>
        </motion.div>
      ))}
    </div>
  );
}
