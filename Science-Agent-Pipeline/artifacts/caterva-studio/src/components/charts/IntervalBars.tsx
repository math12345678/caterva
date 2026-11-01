/**
 * Values with their intervals, side by side: replica means with their
 * errors, a computed free energy against the measured band, Ki rows of one
 * compound. Every value is a SourcedValue, so the table under the chart
 * draws each with its provenance mark, and a bar's colour follows its kind
 * (signal for a measurement, ink for a fit, muted for a computation).
 *
 * Intervals come from the server: `low`/`high` given per item (a band the
 * library computed), or the value's own `interval`. A value without one is
 * drawn without whiskers, never with a guessed error.
 */
import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { SourcedValue } from "@/api/types";
import { Value } from "@/components/provenance/Value";
import { DataTable } from "@/components/table/DataTable";
import { formatNumber } from "@/lib/format";

import { ChartFrame } from "./ChartFrame";
import { AXIS, GRID, tick } from "./theme";

export interface IntervalItem {
  label: string;
  value: SourcedValue;
  low?: number | null;
  high?: number | null;
}

const KIND_FILL: Record<string, string> = {
  measured: "var(--signal)",
  fitted: "var(--fg-soft)",
  computed: "var(--muted)",
  placeholder: "var(--caution)",
  chosen: "var(--fg-soft)",
};

interface Datum {
  label: string;
  v: number;
  err: [number, number] | undefined;
  kind: string;
  low: number | null;
  high: number | null;
}

export function intervalData(items: readonly IntervalItem[]): Datum[] {
  const out: Datum[] = [];
  for (const it of items) {
    const v = it.value.value;
    if (v === null) continue;
    const low = it.low ?? it.value.interval?.low ?? null;
    const high = it.high ?? it.value.interval?.high ?? null;
    const err: [number, number] | undefined =
      low !== null && high !== null ? [Math.max(0, v - low), Math.max(0, high - v)] : undefined;
    out.push({ label: it.label, v, err, kind: it.value.provenance.kind, low, high });
  }
  return out;
}

export function IntervalBars({
  title,
  caption,
  items,
  unit,
  band,
  height,
  width,
}: {
  title: string;
  caption?: string;
  items: readonly IntervalItem[];
  unit: string;
  /** A reference band to hold the values to (the measured band), drawn behind the bars. */
  band?: { low: SourcedValue; high: SourcedValue; label: string } | null;
  height?: number;
  width?: number;
}) {
  const data = useMemo(() => intervalData(items), [items]);
  const without = items.length - data.length;
  const h = height ?? Math.max(160, 44 + data.length * 34);
  const chart = (
    <BarChart
      data={data}
      layout="vertical"
      margin={{ top: 8, right: 24, bottom: 22, left: 8 }}
      width={width}
      height={width ? h : undefined}
      barCategoryGap="28%"
    >
      <CartesianGrid {...GRID} horizontal={false} />
      {band && band.low.value !== null && band.high.value !== null ? (
        <ReferenceArea
          x1={band.low.value}
          x2={band.high.value}
          fill="var(--signal-wash)"
          stroke="var(--signal)"
          strokeDasharray="3 3"
          ifOverflow="extendDomain"
          label={{ value: band.label, position: "insideTopRight", fill: "var(--signal-deep)", fontSize: 11 }}
        />
      ) : null}
      <XAxis
        type="number"
        dataKey="v"
        tickFormatter={tick}
        {...AXIS}
        domain={["auto", "auto"]}
        label={{ value: unit, position: "insideBottom", offset: -12 }}
      />
      <YAxis type="category" dataKey="label" {...AXIS} width={120} tick={{ ...AXIS.tick, fill: "var(--fg-soft)" }} />
      <Tooltip
        isAnimationActive={false}
        cursor={{ fill: "var(--surface-raised)" }}
        formatter={(v: unknown) => (typeof v === "number" ? `${formatNumber(v)} ${unit}` : String(v))}
        wrapperClassName="chart-tooltip"
      />
      <Bar dataKey="v" isAnimationActive={false} maxBarSize={14}>
        {data.map((d) => (
          <Cell key={d.label} fill={KIND_FILL[d.kind] ?? "var(--muted)"} />
        ))}
        <ErrorBar dataKey="err" width={6} strokeWidth={1.5} stroke="var(--fg)" direction="x" />
      </Bar>
    </BarChart>
  );
  return (
    <ChartFrame
      title={title}
      height={h}
      caption={
        <>
          {caption}
          {without ? ` ${without} value${without === 1 ? " has" : "s have"} no number to draw; the table shows why.` : null}
        </>
      }
      table={
        <DataTable
          caption={title}
          captionHidden
          rows={items}
          rowKey={(it) => it.label}
          columns={[
            { key: "label", header: "", cell: (it) => it.label },
            { key: "value", header: "value", numeric: true, cell: (it) => <Value v={it.value} /> },
            {
              key: "interval",
              header: "interval",
              numeric: true,
              cell: (it) => {
                const low = it.low ?? it.value.interval?.low ?? null;
                const high = it.high ?? it.value.interval?.high ?? null;
                return low !== null && high !== null ? `${formatNumber(low)} to ${formatNumber(high)}` : "none given";
              },
            },
          ]}
        />
      }
    >
      {width ? chart : <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer>}
    </ChartFrame>
  );
}
