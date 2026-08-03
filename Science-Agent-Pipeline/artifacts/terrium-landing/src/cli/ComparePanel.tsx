import { motion } from "framer-motion";
import type { SimulationJob } from "@workspace/api-client-react";
import LineChart from "./LineChart";

const COLOR_PALETTES: Record<string, string[]> = {
  S: ["#1D8A72", "#F59E0B"],
  I: ["#EF4444", "#8B5CF6"],
  R: ["#3B82F6", "#F97316"],
  P: ["#F59E0B", "#10B981"],
  E: ["#8B5CF6", "#EC4899"],
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
    { key: `${key} (A)`, color: (COLOR_PALETTES[key] ?? ["#ffffff"])[0]! },
    {
      key: `${key} (B)`,
      color: (COLOR_PALETTES[key] ?? ["#ffffff"])[1] ?? "#888888",
    },
  ]);
  return { data, series, allKeys };
}

function computeRmsdMetrics(
  aTraj: Record<string, number>[],
  bTraj: Record<string, number>[],
  keys: string[],
) {
  const metrics: { key: string; value: number }[] = [];
  for (const key of keys) {
    const aVals = aTraj.map((p) => Number(p[key] ?? 0));
    const bVals = bTraj.map((p) => Number(p[key] ?? 0));
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

  const rmsdMetrics = sameDomain
    ? computeRmsdMetrics(aTraj, bTraj, allKeys)
    : [];

  const extractStats = (traj: Record<string, number>[]) => {
    const peakI =
      traj.length > 0 ? Math.max(...traj.map((p) => Number(p.I ?? 0))) : null;
    const finalS = traj.length > 0 ? traj[traj.length - 1]?.S : null;
    const peakR =
      traj.length > 0 ? Math.max(...traj.map((p) => Number(p.R ?? 0))) : null;
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
      className="rounded-lg border border-[#F59E0B]/20 bg-[#F59E0B]/[0.02] p-4 mb-4"
    >
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] text-[#F59E0B]/60 uppercase tracking-wide font-medium">
          comparison
        </span>
        <button
          onClick={onClear}
          className="text-[9px] text-white/30 hover:text-white/60 border border-white/[0.06] rounded px-2 py-0.5 transition-colors"
        >
          clear
        </button>
      </div>

      <div className="flex items-center gap-3 text-[11px] text-white/30 mb-4">
        <span className="inline-flex items-center gap-1 rounded bg-[#1D8A72]/10 px-2 py-0.5 text-[9px] text-[#1D8A72]">
          Run A &middot; {a.result.domain}
        </span>
        <span className="text-white/20 truncate max-w-[200px]">{a.query}</span>
        <span className="text-white/10">vs</span>
        <span className="inline-flex items-center gap-1 rounded bg-[#F59E0B]/10 px-2 py-0.5 text-[9px] text-[#F59E0B]">
          Run B &middot; {b.result.domain}
        </span>
        <span className="text-white/20 truncate max-w-[200px]">{b.query}</span>
      </div>

      {sameDomain && data.length > 0 && (
        <div className="rounded-lg border border-white/[0.04] bg-white/[0.01] p-2 mb-4">
          <LineChart
            data={data as import("@/lib/simulate").Point[]}
            series={series}
          />
          <div className="flex gap-4 mt-2 px-1 text-[9px] text-white/25">
            <span className="flex items-center gap-1">
              <span
                className="w-2 h-2 rounded-sm inline-block"
                style={{
                  backgroundColor: (COLOR_PALETTES.S ?? ["#1D8A72"])[0],
                }}
              />
              Run A
            </span>
            <span className="flex items-center gap-1">
              <span
                className="w-2 h-2 rounded-sm inline-block"
                style={{
                  backgroundColor:
                    (COLOR_PALETTES.S ?? ["#1D8A72"])[1] ?? "#F59E0B",
                }}
              />
              Run B
            </span>
          </div>
        </div>
      )}

      {rmsdMetrics.length > 0 && (
        <div className="rounded border border-white/[0.06] bg-white/[0.01] p-3 mb-3">
          <div className="text-[9px] text-white/20 uppercase tracking-wide mb-2">
            trajectory divergence (RMSD)
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px]">
            {rmsdMetrics.map((m) => (
              <div key={m.key} className="flex items-center gap-1.5">
                <span className="text-white/25">{m.key}:</span>
                <span
                  className={
                    m.value < 0.01
                      ? "text-[#1D8A72]"
                      : m.value < 1
                        ? "text-[#F59E0B]/70"
                        : "text-[#EF4444]/70"
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
        <div className="rounded border border-white/[0.04] p-2">
          <div className="text-[9px] text-white/20 uppercase tracking-wide mb-1">
            parameters A
          </div>
          <pre className="text-white/50 text-[10px] overflow-x-auto">
            {JSON.stringify(a.result.parameters, null, 2)}
          </pre>
        </div>
        <div className="rounded border border-white/[0.04] p-2">
          <div className="text-[9px] text-white/20 uppercase tracking-wide mb-1">
            parameters B
          </div>
          <pre className="text-white/50 text-[10px] overflow-x-auto">
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
            <div className="text-[8px] text-white/15 uppercase tracking-wide mb-1">
              run A
            </div>
            {statsA.peakI !== null && (
              <div className="flex justify-between">
                <span className="text-white/25">peak I:</span>
                <span className="text-white/50">{statsA.peakI.toFixed(0)}</span>
              </div>
            )}
            {statsA.finalS !== null && (
              <div className="flex justify-between">
                <span className="text-white/25">final S:</span>
                <span className="text-white/50">
                  {statsA.finalS.toFixed(3)}
                </span>
              </div>
            )}
            {statsA.peakR !== null && (
              <div className="flex justify-between">
                <span className="text-white/25">peak R:</span>
                <span className="text-white/50">{statsA.peakR.toFixed(0)}</span>
              </div>
            )}
            {statsA.finalE !== null && (
              <div className="flex justify-between">
                <span className="text-white/25">final E:</span>
                <span className="text-white/50">
                  {statsA.finalE.toFixed(3)}
                </span>
              </div>
            )}
          </div>
          <div className="space-y-1">
            <div className="text-[8px] text-white/15 uppercase tracking-wide mb-1">
              run B
            </div>
            {statsB.peakI !== null && (
              <div className="flex justify-between">
                <span className="text-white/25">peak I:</span>
                <span className="text-white/50">{statsB.peakI.toFixed(0)}</span>
              </div>
            )}
            {statsB.finalS !== null && (
              <div className="flex justify-between">
                <span className="text-white/25">final S:</span>
                <span className="text-white/50">
                  {statsB.finalS.toFixed(3)}
                </span>
              </div>
            )}
            {statsB.peakR !== null && (
              <div className="flex justify-between">
                <span className="text-white/25">peak R:</span>
                <span className="text-white/50">{statsB.peakR.toFixed(0)}</span>
              </div>
            )}
            {statsB.finalE !== null && (
              <div className="flex justify-between">
                <span className="text-white/25">final E:</span>
                <span className="text-white/50">
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
