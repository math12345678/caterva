import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import LineChart from "@/cli/LineChart";
import { simulateMichaelisMenten } from "@/lib/simulate";
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

// km is the real BRENDA-resolved value for this exact query ("lactate
// dehydrogenase with pyruvate"), confirmed live against the running
// pipeline -- not a placeholder. vmax has no literature-resolution path
// in this system (it's always user-supplied), so it stays illustrative;
// the description below reflects that split rather than claiming both.
const MM_EXAMPLE = simulateMichaelisMenten({
  km: 10.73,
  vmax: 5,
  s0: 10,
  end: 3,
  points: 61,
});
// Competitive inhibition of human LDH-A by oxamate. A competitive inhibitor
// leaves the rate law in Michaelis-Menten form with Km scaled by
// (1 + [I]/Ki), so the same integrator is exact here -- no second model.
// Km 0.03 mM (BRENDA ref 286469) and Ki 0.00059 mM (BRENDA ref 739793) are
// both Homo sapiens, pyruvate; [I], Vmax and [S]0 are chosen.
const LDH_KM = 0.03;
const OXAMATE_KI = 0.00059;
const OXAMATE_I = 0.001;
const LDH_FREE = simulateMichaelisMenten({ km: LDH_KM, vmax: 0.05, s0: 0.2, end: 6, points: 61 });
const LDH_INHIBITED = simulateMichaelisMenten({
  km: LDH_KM * (1 + OXAMATE_I / OXAMATE_KI),
  vmax: 0.05,
  s0: 0.2,
  end: 6,
  points: 61,
});
const LDH_BOTH = LDH_FREE.trajectory.map((p, i) => ({
  t: p.t,
  S: p.S,
  S_inhibited: LDH_INHIBITED.trajectory[i]!.S,
}));

const EXAMPLES: ExampleCard[] = [
  {
    id: "mm-demo",
    domain: "mm",
    label: "Michaelis-Menten",
    // "literature-verified" was an overclaim, and specifically the kind
    // this product exists to refuse. Re-resolved live: the value and the
    // source are real (BRENDA ref 740253, EC 1.1.1.27, Homo sapiens), but
    // the pipeline returns citationStatus "flagged", not "verified",
    // because the source never reported assay temperature and STRENDA
    // requires it for kinetic data. Caterva's own resolver declines to
    // call this value verified; the page must not call it verified over
    // the resolver's head.
    description:
      "Enzyme kinetics — Km is a real BRENDA value (10.73 mM, EC 1.1.1.27, " +
      "H. sapiens), flagged rather than verified because the source did not " +
      "report assay temperature. Vmax is user-chosen.",
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
      series: [{ key: "S", color: "#5D7F8D" }],
    },
    query: "simulate lactate dehydrogenase with pyruvate",
  },
  {
    id: "ldh-oxamate-demo",
    domain: "mm_competitive_inhibition",
    label: "Competitive inhibition",
    description:
      "Human LDH-A with and without oxamate. Km 0.03 mM (BRENDA ref 286469) " +
      "and Ki 0.00059 mM (BRENDA ref 739793), both measured in H. sapiens; " +
      "the inhibitor raises the apparent Km and leaves Vmax untouched.",
    stats: [
      { label: "apparent Km", value: (LDH_KM * (1 + OXAMATE_I / OXAMATE_KI)).toFixed(3) + " mM" },
      {
        label: "[S] left at t=6",
        value:
          LDH_INHIBITED.trajectory[LDH_INHIBITED.trajectory.length - 1]!.S.toFixed(3) +
          " vs " +
          LDH_FREE.trajectory[LDH_FREE.trajectory.length - 1]!.S.toFixed(3) +
          " mM",
      },
    ],
    chart: {
      data: LDH_BOTH,
      series: [
        { key: "S", color: "#5D7F8D" },
        { key: "S_inhibited", color: "#946522" },
      ],
    },
    query: "competitive inhibition of lactate dehydrogenase by oxamate",
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
          className="group rounded-lg border border-fg/[0.12] bg-fg/[0.015] overflow-hidden transition-all duration-300 hover:border-signal/20 hover:bg-signal/[0.02]"
        >
          <div className="p-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center rounded bg-signal/10 px-1.5 py-0.5 text-[9px] text-signal uppercase tracking-wide">
                {example.domain}
              </span>
              <span className="text-fg/80 text-[11px] font-medium">
                {example.label}
              </span>
            </div>
            <p className="text-fg/66 text-[10px] mb-3 leading-relaxed">
              {example.description}
            </p>

            <div className="rounded border border-fg/[0.08] bg-fg/[0.01] p-1.5 mb-3">
              <LineChart
                data={example.chart.data}
                series={example.chart.series}
              />
            </div>

            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] mb-3">
              {example.stats.map((s) => (
                <span key={s.label} className="text-fg/70">
                  {s.label}: <span className="text-fg/80">{s.value}</span>
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
              className="w-full rounded-md border border-signal/15 text-[10px] text-signal/60 py-1.5 transition-all duration-200 hover:bg-signal/[0.06] hover:text-signal"
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
