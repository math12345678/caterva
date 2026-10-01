/**
 * C-alpha RMSF along the chain, one line per replica: where the protein
 * moved, not only the two averages the flexibility table gives. The pocket
 * residues (those the pocket mean is taken over) are shaded, and the
 * catalytic residues marked, both as the server listed them.
 *
 * The values are the series the analyze adapter sent
 * (`flexibility.rmsf`), drawn as given: a residue a replica has no value
 * for is a gap, never bridged. The table under the chart gives each value
 * with the series' provenance, which is one measurement for all of them.
 */
import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { SourcedValue } from "@/api/types";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { AXIS, GRID, seriesColor, seriesDash, tick } from "@/components/charts/theme";
import { ProvenanceMark, provenanceLabel } from "@/components/provenance/ProvenanceMark";
import { Value } from "@/components/provenance/Value";
import { DataTable } from "@/components/table/DataTable";
import { formatNumber } from "@/lib/format";

import type { RmsfProfileView } from "./views";

type Row = { residue: number } & Record<string, number | null>;

/** Consecutive residue numbers in `pocket`, as [first, last] runs, for shading. */
export function runs(numbers: readonly number[]): [number, number][] {
  const sorted = [...numbers].sort((a, b) => a - b);
  const out: [number, number][] = [];
  for (const n of sorted) {
    const last = out[out.length - 1];
    if (last && n === last[1] + 1) last[1] = n;
    else out.push([n, n]);
  }
  return out;
}

function RmsfTooltip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number | null }[];
  label?: number;
  unit: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <span className="chart-tooltip-label">residue {label}</span>
      {payload.map((p) => (
        <span key={p.name}>
          {p.name} {typeof p.value === "number" ? `${formatNumber(p.value)} ${unit}` : "none"}
        </span>
      ))}
    </div>
  );
}

export function RmsfChart({ profile, width, height = 260 }: { profile: RmsfProfileView; width?: number; height?: number }) {
  const names = useMemo(() => Object.keys(profile.replicas), [profile]);
  const rows = useMemo<Row[]>(
    () =>
      profile.residues.map((residue, i) => {
        const row = { residue } as Row;
        for (const n of names) row[n] = profile.replicas[n][i] ?? null;
        return row;
      }),
    [profile, names],
  );
  const pocketRuns = useMemo(() => runs(profile.pocket), [profile]);
  const value = (n: string, r: Row): SourcedValue | null =>
    r[n] === null ? null : { value: r[n] as number, unit: profile.unit, provenance: profile.provenance, label: `residue ${r.residue} RMSF, ${n}` };

  const chart = (
    <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 22, left: 8 }} width={width} height={width ? height : undefined}>
      <CartesianGrid {...GRID} vertical={false} />
      {pocketRuns.map(([a, b]) => (
        <ReferenceArea key={a} x1={a - 0.5} x2={b + 0.5} fill="var(--signal-wash)" fillOpacity={1} ifOverflow="extendDomain" />
      ))}
      {profile.catalytic.map((r) => (
        <ReferenceLine key={r} x={r} stroke="var(--signal)" strokeDasharray="3 3" />
      ))}
      <XAxis
        dataKey="residue"
        type="number"
        domain={["dataMin", "dataMax"]}
        allowDecimals={false}
        tickFormatter={tick}
        {...AXIS}
        label={{ value: "residue", position: "insideBottom", offset: -12 }}
      />
      <YAxis tickFormatter={tick} {...AXIS} width={56} label={{ value: profile.unit, angle: -90, position: "insideLeft" }} />
      <Tooltip content={<RmsfTooltip unit={profile.unit} />} cursor={{ stroke: "var(--rule-strong)" }} isAnimationActive={false} />
      {names.map((n, i) => (
        <Line
          key={n}
          dataKey={n}
          name={n}
          type="linear"
          stroke={seriesColor(i)}
          strokeDasharray={seriesDash(i)}
          strokeWidth={1.5}
          dot={false}
          activeDot={{ r: 3 }}
          connectNulls={false}
          isAnimationActive={false}
        />
      ))}
    </LineChart>
  );

  return (
    <ChartFrame
      title="C-alpha RMSF along the chain"
      height={height}
      legend={names.map((n, i) => ({ label: n, index: i }))}
      caption={
        <span className="st-inline">
          <ProvenanceMark provenance={profile.provenance} decorative />
          {provenanceLabel(profile.provenance)}: {profile.provenance.method}. Shaded: the {profile.pocket.length} pocket
          residues; dashed: the catalytic residues.
        </span>
      }
      table={
        <DataTable
          caption={`C-alpha RMSF of ${rows.length} residues`}
          captionHidden
          rows={rows}
          rowKey={(r) => String(r.residue)}
          columns={[
            { key: "residue", header: "residue", numeric: true, cell: (r) => r.residue, sortValue: (r) => r.residue },
            {
              key: "where",
              header: "",
              cell: (r) =>
                profile.catalytic.includes(r.residue) ? "catalytic" : profile.pocket.includes(r.residue) ? "pocket" : "",
            },
            ...names.map((n) => ({
              key: n,
              header: n,
              numeric: true,
              sortValue: (r: Row) => r[n] as number | null,
              cell: (r: Row) => {
                const v = value(n, r);
                return v ? <Value v={v} /> : <span className="muted">none</span>;
              },
            })),
          ]}
        />
      }
    >
      {width ? chart : <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer>}
    </ChartFrame>
  );
}
