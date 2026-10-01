/**
 * A response against a dose or a concentration: measured points as dots,
 * and a curve when the server sent one (a fit, a sweep of the model). The
 * curve is never computed here: a line the page drew through points would
 * be a fit nobody can cite. Each layer's legend entry wears the mark of
 * its provenance kind, so "measured" and "fitted" read apart at a glance.
 */
import { useMemo } from "react";
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";

import type { ProvenanceKind } from "@/api/types";
import { ProvenanceMark, provenanceLabel } from "@/components/provenance/ProvenanceMark";
import { DataTable } from "@/components/table/DataTable";
import { formatNumber } from "@/lib/format";

import { ChartFrame } from "./ChartFrame";
import { AXIS, GRID, tick } from "./theme";

export interface XY {
  x: number;
  y: number;
}

export function DoseResponseChart({
  title,
  caption,
  points,
  pointsKind,
  curve,
  curveKind,
  xLabel,
  xUnit,
  yLabel,
  yUnit,
  logX = false,
  height = 300,
  width,
}: {
  title: string;
  caption?: string;
  points: readonly XY[];
  pointsKind: ProvenanceKind;
  curve?: readonly XY[];
  curveKind?: ProvenanceKind;
  xLabel: string;
  xUnit: string;
  yLabel: string;
  yUnit: string;
  logX?: boolean;
  height?: number;
  width?: number;
}) {
  // A log axis cannot place zero or a negative dose; those points are listed in the table and said to be omitted.
  const plotted = useMemo(() => (logX ? points.filter((p) => p.x > 0) : [...points]), [points, logX]);
  const plottedCurve = useMemo(() => (curve ? (logX ? curve.filter((p) => p.x > 0) : [...curve]) : []), [curve, logX]);
  const omitted = points.length - plotted.length;
  const chart = (
    <ComposedChart margin={{ top: 8, right: 16, bottom: 22, left: 8 }} width={width} height={width ? height : undefined}>
      <CartesianGrid {...GRID} />
      <XAxis
        dataKey="x"
        type="number"
        scale={logX ? "log" : "auto"}
        domain={["auto", "auto"]}
        allowDataOverflow={false}
        tickFormatter={tick}
        {...AXIS}
        label={{ value: `${xLabel} (${xUnit})`, position: "insideBottom", offset: -12 }}
      />
      <YAxis
        dataKey="y"
        type="number"
        tickFormatter={tick}
        {...AXIS}
        width={56}
        label={{ value: `${yLabel} (${yUnit})`, angle: -90, position: "insideLeft" }}
      />
      <Tooltip
        isAnimationActive={false}
        cursor={{ stroke: "var(--rule-strong)" }}
        formatter={(v: unknown) => (typeof v === "number" ? formatNumber(v) : String(v))}
        labelFormatter={(v: unknown) => (typeof v === "number" ? `${xLabel} ${formatNumber(v)} ${xUnit}` : "")}
        wrapperClassName="chart-tooltip"
      />
      {plottedCurve.length ? (
        <Line
          data={plottedCurve}
          dataKey="y"
          name={curveKind ? provenanceLabel({ kind: curveKind }) : "curve"}
          type="linear"
          stroke="var(--series-2)"
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      ) : null}
      <Scatter
        data={plotted}
        dataKey="y"
        name={provenanceLabel({ kind: pointsKind })}
        fill={pointsKind === "measured" ? "var(--signal)" : "var(--series-1)"}
        isAnimationActive={false}
      />
    </ComposedChart>
  );
  return (
    <ChartFrame
      title={title}
      height={height}
      caption={
        <>
          <span className="chart-kinds">
            <ProvenanceMark provenance={{ kind: pointsKind }} decorative /> points: {provenanceLabel({ kind: pointsKind })}
            {curveKind && plottedCurve.length ? (
              <>
                {" "}
                <ProvenanceMark provenance={{ kind: curveKind }} decorative /> line: {provenanceLabel({ kind: curveKind })}
              </>
            ) : null}
          </span>
          {caption ? <> {caption}</> : null}
          {omitted ? ` ${omitted} point${omitted === 1 ? "" : "s"} at zero or below cannot be placed on a log axis; the table lists them.` : null}
        </>
      }
      table={
        <DataTable
          caption={`${title}: ${points.length} points`}
          captionHidden
          rows={points}
          rowKey={(_, i) => String(i)}
          columns={[
            { key: "x", header: `${xLabel} (${xUnit})`, numeric: true, cell: (p) => formatNumber(p.x), sortValue: (p) => p.x },
            { key: "y", header: `${yLabel} (${yUnit})`, numeric: true, cell: (p) => formatNumber(p.y), sortValue: (p) => p.y },
          ]}
        />
      }
    >
      {width ? chart : <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer>}
    </ChartFrame>
  );
}
