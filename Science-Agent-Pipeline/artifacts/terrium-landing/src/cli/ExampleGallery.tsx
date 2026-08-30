import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import LineChart from "@/cli/LineChart";
import { simulateMichaelisMenten, simulateSIR } from "@/lib/simulate";
import type { Point } from "@/lib/simulate";

interface ExampleCard {
  id: string;
  domain: string;
  label: string;
  description: string;
  stats: { label: string; value: string }[];
  chart: { data: Point[]; series: { key: string; color: string }[] };
  query: string;
}

const MM_EXAMPLE = simulateMichaelisMenten({
  km: 2,
  vmax: 5,
  s0: 10,
  end: 3,
  points: 61,
});
const SIR_EXAMPLE = simulateSIR({
  beta: 0.3,
  gamma: 0.1,
  s0: 990,
  i0: 10,
  end: 100,
  points: 101,
});
// Same SIR integrator as SIR_EXAMPLE, just higher beta / lower gamma --
// there is no E compartment here, so this must not be labeled SEIR.
const SIR_HIGH_R0_EXAMPLE = simulateSIR({
  beta: 0.35,
  gamma: 0.05,
  s0: 990,
  i0: 10,
  end: 100,
  points: 101,
});

const EXAMPLES: ExampleCard[] = [
  {
    id: "mm-demo",
    domain: "mm",
    label: "Michaelis-Menten",
    description: "Enzyme kinetics with literature-verified Km and Vmax values.",
    stats: [
      {
        label: "final [S]",
        value:
          MM_EXAMPLE.trajectory[MM_EXAMPLE.trajectory.length - 1].S.toFixed(3) +
          " mM",
      },
      { label: "residual", value: MM_EXAMPLE.finalResidual.toExponential(2) },
    ],
    chart: {
      data: MM_EXAMPLE.trajectory,
      series: [{ key: "S", color: "#1D8A72" }],
    },
    query: "simulate lactate dehydrogenase with pyruvate",
  },
  {
    id: "sir-demo",
    domain: "sir",
    label: "SIR Outbreak",
    description:
      "Epidemiological spread with population conservation checking.",
    stats: [
      {
        label: "peak infected",
        value: Math.max(...SIR_EXAMPLE.trajectory.map((p) => p.I)).toFixed(0),
      },
      { label: "R\u2080", value: (0.3 / 0.1).toFixed(2) },
    ],
    chart: {
      data: SIR_EXAMPLE.trajectory,
      series: [
        { key: "S", color: "#3B82F6" },
        { key: "I", color: "#EF4444" },
        { key: "R", color: "#1D8A72" },
      ],
    },
    query: "model an outbreak with beta 0.3 and gamma 0.1",
  },
  {
    id: "sir-high-r0-demo",
    domain: "sir",
    label: "SIR (High R\u2080)",
    description:
      "Same SIR model with higher transmission and slower recovery, giving a higher R\u2080.",
    stats: [
      {
        label: "peak infected",
        value: Math.max(...SIR_HIGH_R0_EXAMPLE.trajectory.map((p) => p.I)).toFixed(0),
      },
      { label: "R\u2080", value: (0.35 / 0.05).toFixed(2) },
    ],
    chart: {
      data: SIR_HIGH_R0_EXAMPLE.trajectory,
      series: [
        { key: "S", color: "#3B82F6" },
        { key: "I", color: "#EF4444" },
        { key: "R", color: "#1D8A72" },
      ],
    },
    query: "model an outbreak with beta 0.35 and gamma 0.05",
  },
];

interface ExampleGalleryProps {
  onTryQuery: (query: string) => void;
}

export default function ExampleGallery({ onTryQuery }: ExampleGalleryProps) {
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {EXAMPLES.map((example) => (
        <motion.div
          key={example.id}
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          onMouseEnter={() => setHovered(example.id)}
          onMouseLeave={() => setHovered(null)}
          className="group rounded-lg border border-white/[0.06] bg-white/[0.015] overflow-hidden transition-all duration-300 hover:border-[#1D8A72]/20 hover:bg-[#1D8A72]/[0.02]"
        >
          <div className="p-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center rounded bg-[#1D8A72]/10 px-1.5 py-0.5 text-[9px] text-[#1D8A72] uppercase tracking-wide">
                {example.domain}
              </span>
              <span className="text-white/60 text-[11px] font-medium">
                {example.label}
              </span>
            </div>
            <p className="text-white/25 text-[10px] mb-3 leading-relaxed">
              {example.description}
            </p>

            <div className="rounded border border-white/[0.04] bg-white/[0.01] p-1.5 mb-3">
              <LineChart
                data={example.chart.data}
                series={example.chart.series}
              />
            </div>

            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] mb-3">
              {example.stats.map((s) => (
                <span key={s.label} className="text-white/30">
                  {s.label}: <span className="text-white/60">{s.value}</span>
                </span>
              ))}
            </div>

            <motion.button
              onClick={() => {
                onTryQuery(example.query);
                setTimeout(() => {
                  document
                    .getElementById("agent")
                    ?.scrollIntoView({ behavior: "smooth", block: "start" });
                }, 100);
              }}
              className="w-full rounded-md border border-[#1D8A72]/15 text-[10px] text-[#1D8A72]/60 py-1.5 transition-all duration-200 hover:bg-[#1D8A72]/[0.06] hover:text-[#1D8A72]"
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
            >
              try it &rarr;
            </motion.button>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
