import { motion } from "framer-motion";
import type { SimulationJob } from "@workspace/api-client-react";
import LineChart from "./LineChart";

const COLOR_PALETTES: Record<string, string[]> = {
  S: ["#5D7F8D", "#946522"],
  I: ["#A63D35", "#6A6E78"],
  R: ["#6A6E78", "#946522"],
  P: ["#946522", "#5D7F8D"],
  E: ["#6A6E78", "#6A6E78"],
};

function rmsd(a: number[], b: number[]): number {
  const len = Math.min(a.length, b.length);
  if (len === 0) return 0;
  let sum = 0;
  for (let i = 0; i < len; i++) {
    sum += (a[i]! - b[i]!) ** 2;
  }
  return Math.sqrt(sum / len);
}

function seriesForComparison(a: SimulationJob, b: SimulationJob) {
  const aTraj = a.result!.trajectory!;
  const bTraj = b.result!.trajectory!;
  if (aTraj.length === 0 || bTraj.length === 0)
    return { data: [], series: [], allKeys: [] as string[] };
  const keysA = Object.keys(aTraj[0]!).filter((k) => k !== "t");
  const keysB = Object.keys(bTraj[0]!).filter((k) => k !== "t");
  const allKeys = [...new Set([...keysA, ...keysB])];
  const maxLen = Math.max(aTraj.length, bTraj.length);
  const data = Array.from({ length: maxLen }, (_, i) => {
    const pa = aTraj[Math.floor((i / maxLen) * aTraj.length)] as
      Record<string, number> | undefined;
    const pb = bTraj[Math.floor((i / maxLen) * bTraj.length)] as
      Record<string, number> | undefined;
    const t = (pa?.t ?? pb?.t ?? i) as number;
    const point: Record<string, number> = { t };
    for (const key of allKeys) {
      const palette = COLOR_PALETTES[key];
      if (palette) {
        point[`${key} (A)`] = Number(pa?.[key] ?? 0);
        point[`${key} (B)`] = Number(pb?.[key] ?? 0);
      } else {
        point[`${key} (A)`] = Number(pa?.[key] ?? 0);
        point[`${key} (B)`] = Number(pb?.[key] ?? 0);
      }
    }
    return point;
  });
  const series = allKeys.flatMap((key) => [
    { key: `${key} (A)`, color: (COLOR_PALETTES[key] ?? ["#FDF8EE"])[0]! },
    {
      key: `${key} (B)`,
      color: (COLOR_PALETTES[key] ?? ["#FDF8EE"])[1] ?? "#888888",
    },
  ]);
  return { data, series, allKeys };
}

function computeRmsdMetrics(data: Record<string, number>[], keys: string[]) {
  // data is the already-resampled chart series, so A/B are compared at
  // matched positions even when the two runs have different point counts.
  const metrics: { key: string; value: number }[] = [];
  for (const key of keys) {
    const aVals = data.map((p) => Number(p[`${key} (A)`] ?? 0));
    const bVals = data.map((p) => Number(p[`${key} (B)`] ?? 0));
    metrics.push({ key, value: rmsd(aVals, bVals) });
  }
  return metrics;
}

interface Props {
  runs: SimulationJob[];
  onClear: () => void;
}

export default function ComparePanel({ runs, onClear }: Props) {
  const [a, b] = runs;
  if (!a || !b || !a.result || !b.result) return null;

  const sameDomain = a.result.domain === b.result.domain;
  const { data, series, allKeys } = sameDomain
    ? seriesForComparison(a, b)
    : { data: [], series: [], allKeys: [] as string[] };

  const aTraj = (a.result.trajectory ?? []) as Record<string, number>[];
  const bTraj = (b.result.trajectory ?? []) as Record<string, number>[];

  const rmsdMetrics = sameDomain ? computeRmsdMetrics(data, allKeys) : [];

  const extractStats = (traj: Record<string, number>[]) => {
    const hasI = traj.length > 0 && "I" in traj[0]!;
    const peakI = hasI
      ? Math.max(...traj.map((p) => Number(p.I ?? 0)))
      : null;
    const finalS = traj.length > 0 ? traj[traj.length - 1]?.S : null;
    const hasR = traj.length > 0 && "R" in traj[0]!;
    const peakR = hasR
      ? Math.max(...traj.map((p) => Number(p.R ?? 0)))
      : null;
    const finalE = traj.length > 0 ? traj[traj.length - 1]?.E : null;
    return {
      peakI: peakI as number | null,
      finalS: (finalS as number | undefined) ?? null,
      peakR: peakR as number | null,
      finalE: (finalE as number | undefined) ?? null,
    };
  };

  const statsA = extractStats(aTraj);
  const statsB = extractStats(bTraj);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-lg border border-caution/20 bg-caution/[0.02] p-4 mb-4"
    >
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] text-caution/60 uppercase tracking-wide font-medium">
          comparison
        </span>
        <button
          onClick={onClear}
          className="text-[9px] text-fg/70 hover:text-fg/80 border border-fg/[0.12] rounded px-2 py-0.5 transition-colors"
        >
          clear
        </button>
      </div>

      <div className="flex items-center gap-3 text-[11px] text-fg/70 mb-4">
        <span className="inline-flex items-center gap-1 rounded bg-signal/10 px-2 py-0.5 text-[9px] text-signal">
          Run A &middot; {a.result.domain}
        </span>
        <span className="text-fg/66 truncate max-w-[200px]">{a.query}</span>
        <span className="text-fg/66">vs</span>
        <span className="inline-flex items-center gap-1 rounded bg-caution/10 px-2 py-0.5 text-[9px] text-caution">
          Run B &middot; {b.result.domain}
        </span>
        <span className="text-fg/66 truncate max-w-[200px]">{b.query}</span>
      </div>

      {sameDomain && data.length > 0 && (
        <div className="rounded-lg border border-fg/[0.08] bg-fg/[0.01] p-2 mb-4">
          <LineChart
            data={data as import("@/lib/simulate").Point[]}
            series={series}
          />
          <div className="flex gap-4 mt-2 px-1 text-[9px] text-fg/66">
            <span className="flex items-center gap-1">
              <span
                className="w-2 h-2 rounded-sm inline-block"
                style={{
                  backgroundColor: (COLOR_PALETTES.S ?? ["#5D7F8D"])[0],
                }}
              />
              Run A
            </span>
            <span className="flex items-center gap-1">
              <span
                className="w-2 h-2 rounded-sm inline-block"
                style={{
                  backgroundColor:
                    (COLOR_PALETTES.S ?? ["#5D7F8D"])[1] ?? "#946522",
                }}
              />
              Run B
            </span>
          </div>
        </div>
      )}

      {rmsdMetrics.length > 0 && (
        <div className="rounded border border-fg/[0.12] bg-fg/[0.01] p-3 mb-3">
          <div className="text-[9px] text-fg/66 uppercase tracking-wide mb-2">
            trajectory divergence (RMSD)
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px]">
            {rmsdMetrics.map((m) => (
              <div key={m.key} className="flex items-center gap-1.5">
                <span className="text-fg/66">{m.key}:</span>
                <span
                  className={
                    m.value < 0.01
                      ? "text-signal"
                      : m.value < 1
                        ? "text-caution/70"
                        : "text-danger/70"
                  }
                >
                  {m.value < 0.001 ? "<0.001" : m.value.toFixed(4)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 text-[11px]">
        <div className="rounded border border-fg/[0.08] p-2">
          <div className="text-[9px] text-fg/66 uppercase tracking-wide mb-1">
            parameters A
          </div>
          <pre className="text-fg/76 text-[10px] overflow-x-auto">
            {JSON.stringify(a.result.parameters, null, 2)}
          </pre>
        </div>
        <div className="rounded border border-fg/[0.08] p-2">
          <div className="text-[9px] text-fg/66 uppercase tracking-wide mb-1">
            parameters B
          </div>
          <pre className="text-fg/76 text-[10px] overflow-x-auto">
            {JSON.stringify(b.result.parameters, null, 2)}
          </pre>
        </div>
      </div>

      {(statsA.peakI !== null ||
        statsA.finalS !== null ||
        statsA.peakR !== null ||
        statsA.finalE !== null ||
        statsB.peakI !== null ||
        statsB.finalS !== null ||
        statsB.peakR !== null ||
        statsB.finalE !== null) && (
        <div className="grid grid-cols-2 gap-3 mt-3 text-[10px]">
          <div className="space-y-1">
            <div className="text-[8px] text-fg/66 uppercase tracking-wide mb-1">
              run A
            </div>
            {statsA.peakI !== null && (
              <div className="flex justify-between">
                <span className="text-fg/66">peak I:</span>
                <span className="text-fg/76">{statsA.peakI.toFixed(0)}</span>
              </div>
            )}
            {statsA.finalS !== null && (
              <div className="flex justify-between">
                <span className="text-fg/66">final S:</span>
                <span className="text-fg/76">
                  {statsA.finalS.toFixed(3)}
                </span>
              </div>
            )}
            {statsA.peakR !== null && (
              <div className="flex justify-between">
                <span className="text-fg/66">peak R:</span>
                <span className="text-fg/76">{statsA.peakR.toFixed(0)}</span>
              </div>
            )}
            {statsA.finalE !== null && (
              <div className="flex justify-between">
                <span className="text-fg/66">final E:</span>
                <span className="text-fg/76">
                  {statsA.finalE.toFixed(3)}
                </span>
              </div>
            )}
          </div>
          <div className="space-y-1">
            <div className="text-[8px] text-fg/66 uppercase tracking-wide mb-1">
              run B
            </div>
            {statsB.peakI !== null && (
              <div className="flex justify-between">
                <span className="text-fg/66">peak I:</span>
                <span className="text-fg/76">{statsB.peakI.toFixed(0)}</span>
              </div>
            )}
            {statsB.finalS !== null && (
              <div className="flex justify-between">
                <span className="text-fg/66">final S:</span>
                <span className="text-fg/76">
                  {statsB.finalS.toFixed(3)}
                </span>
              </div>
            )}
            {statsB.peakR !== null && (
              <div className="flex justify-between">
                <span className="text-fg/66">peak R:</span>
                <span className="text-fg/76">{statsB.peakR.toFixed(0)}</span>
              </div>
            )}
            {statsB.finalE !== null && (
              <div className="flex justify-between">
                <span className="text-fg/66">final E:</span>
                <span className="text-fg/76">
                  {statsB.finalE.toFixed(3)}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
}
