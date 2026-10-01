/**
 * Replicas side by side: one row per quantity (a catalytic distance, an
 * angle), on one axis for the section, each replica's mean as a dot with
 * its block-averaged error as whiskers, the crystal value as a tick, and
 * the mean across replicas with its 95% interval as a band. Agreement is
 * then something the eye reads before the verdict says it.
 *
 * Drawing only. Every position is a value the server sent (a mean, an
 * error, a crystal value, an interval half-width) placed on the axis; the
 * numbers themselves are in the table under the plot, each drawn by Value
 * with its provenance, and the plot is hidden from assistive technology so
 * it never stands in for them. A replica whose mean is not a number is left
 * out of its row, never placed.
 */
import { scaleLinear } from "d3-scale";
import { useMemo } from "react";

import type { SourcedValue } from "@/api/types";
import { SeriesSwatch, seriesColor, tick } from "@/components/charts/theme";

import { Verdict } from "./kit";

export interface ForestRow {
  label: string;
  crystal: SourcedValue | null;
  mean: SourcedValue;
  ci95: SourcedValue | null | undefined;
  replicas: { name: string; mean: SourcedValue; error: SourcedValue | null }[];
  verdict: string;
  reasons?: string[];
}

const H = 22;
/** Horizontal positions are percentages of the plot's width, so marks keep their shape at any width. */
const PAD = 2;
const pc = (v: number) => `${v}%`;

function num(v: SourcedValue | null | undefined): number | null {
  return v && typeof v.value === "number" && Number.isFinite(v.value) ? v.value : null;
}

export function forestDomain(rows: readonly ForestRow[]): [number, number] | null {
  const xs: number[] = [];
  for (const r of rows) {
    const c = num(r.crystal);
    if (c !== null) xs.push(c);
    const m = num(r.mean);
    const ci = num(r.ci95);
    if (m !== null) {
      xs.push(m);
      if (ci !== null) xs.push(m - ci, m + ci);
    }
    for (const p of r.replicas) {
      const pm = num(p.mean);
      const e = num(p.error) ?? 0;
      if (pm !== null) xs.push(pm - e, pm + e);
    }
  }
  if (!xs.length) return null;
  const lo = Math.min(...xs);
  const hi = Math.max(...xs);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.04;
  return [lo - pad, hi + pad];
}

export function ReplicaForest({
  rows,
  unit,
  replicas,
  title,
}: {
  rows: readonly ForestRow[];
  unit: string;
  replicas: readonly string[];
  title: string;
}) {
  const domain = useMemo(() => forestDomain(rows), [rows]);
  const x = useMemo(() => (domain ? scaleLinear().domain(domain).range([PAD, 100 - PAD]).nice() : null), [domain]);
  if (!x) return null;
  const ticks = x.ticks(5);
  return (
    <figure className="chart" aria-label={`${title}: each replica's mean and error, the crystal value and the mean across replicas, on one axis. The numbers are in the table below.`}>
      <div className="chart-head">
        <h3 className="chart-title">{title}</h3>
        <ul className="chart-legend" aria-hidden="true">
          {replicas.map((name, i) => (
            <li key={name}>
              <SeriesSwatch index={i} />
              <span className="font-mono">{name}</span>
            </li>
          ))}
          <li>
            <svg width="10" height="12" viewBox="0 0 10 12" aria-hidden="true">
              <line x1="5" y1="1" x2="5" y2="11" stroke="var(--fg)" strokeWidth="2" />
            </svg>
            crystal
          </li>
          <li>
            <svg width="18" height="10" viewBox="0 0 18 10" aria-hidden="true">
              <rect x="1" y="2" width="16" height="6" fill="var(--signal-wash)" stroke="var(--signal)" />
            </svg>
            mean of replicas, 95% CI
          </li>
        </ul>
      </div>
      <div className="st-forest" aria-hidden="true">
        <div className="st-forest-head">
          <span />
          <span className="st-forest-axis">
            <svg height={20}>
              {ticks.map((t) => (
                <g key={t}>
                  <line x1={pc(x(t))} x2={pc(x(t))} y1={14} y2={20} stroke="var(--rule-strong)" />
                  <text x={pc(x(t))} y={10} textAnchor="middle">
                    {tick(t)}
                  </text>
                </g>
              ))}
            </svg>
          </span>
          <span>{unit}</span>
        </div>
        {rows.map((r) => {
          const m = num(r.mean);
          const ci = num(r.ci95);
          const c = num(r.crystal);
          const n = r.replicas.length;
          return (
            <div className="st-forest-row" key={r.label}>
              <span className="st-forest-label">{r.label}</span>
              <span>
                <svg height={H}>
                  {ticks.map((t) => (
                    <line key={t} x1={pc(x(t))} x2={pc(x(t))} y1={0} y2={H} stroke="var(--rule)" strokeDasharray="2 3" />
                  ))}
                  {m !== null && ci !== null ? (
                    <rect
                      x={pc(x(m - ci))}
                      width={pc(Math.max(0.3, x(m + ci) - x(m - ci)))}
                      y={3}
                      height={H - 6}
                      fill="var(--signal-wash)"
                      stroke="var(--signal)"
                    />
                  ) : null}
                  {m !== null ? <line x1={pc(x(m))} x2={pc(x(m))} y1={3} y2={H - 3} stroke="var(--signal-deep)" /> : null}
                  {c !== null ? <line x1={pc(x(c))} x2={pc(x(c))} y1={1} y2={H - 1} stroke="var(--fg)" strokeWidth={2} /> : null}
                  {r.replicas.map((p, i) => {
                    const pm = num(p.mean);
                    if (pm === null) return null;
                    const e = num(p.error);
                    const y = n > 1 ? 5 + ((H - 10) * i) / (n - 1) : H / 2;
                    const colour = seriesColor(replicas.indexOf(p.name) === -1 ? i : replicas.indexOf(p.name));
                    return (
                      <g key={p.name}>
                        {e !== null ? (
                          <line x1={pc(x(pm - e))} x2={pc(x(pm + e))} y1={y} y2={y} stroke={colour} strokeWidth={1.5} />
                        ) : null}
                        <circle cx={pc(x(pm))} cy={y} r={3.4} fill={colour} />
                      </g>
                    );
                  })}
                </svg>
              </span>
              <span title={r.reasons?.join("; ")}>
                <Verdict word={r.verdict} />
              </span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}
