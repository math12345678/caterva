/**
 * Amounts against time: an ODE trajectory from compose, a Gillespie
 * trajectory from sim. Each series is a column the server sent, drawn as
 * given; a gap (null, a non-finite value the server could not send) is a
 * gap in the line, never bridged. A stochastic trajectory is drawn as
 * steps (`step`), because between events nothing changes.
 */
import { useMemo } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { DataTable } from "@/components/table/DataTable";
import { formatNumber } from "@/lib/format";

import { ChartFrame } from "./ChartFrame";
import { AXIS, GRID, seriesColor, seriesDash, tick } from "./theme";

type Row = { t: number | null } & Record<string, number | null>;

export function timeCourseRows(times: readonly (number | null)[], series: Record<string, readonly (number | null)[]>): Row[] {
  const names = Object.keys(series);
  return times.map((t, i) => {
    const row: Row = { t } as Row;
    for (const n of names) row[n] = series[n][i] ?? null;
    return row;
  });
}

function ChartTooltip({
  active,
  payload,
  label,
  timeUnit,
  unit,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number | null; color?: string }[];
  label?: number;
  timeUnit: string;
  unit: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <span className="chart-tooltip-label">
        t = {typeof label === "number" ? formatNumber(label) : ""} {timeUnit}
      </span>
      {payload.map((p) => (
        <span key={p.name}>
          {p.name} {typeof p.value === "number" ? formatNumber(p.value) : "none"} {unit}
        </span>
      ))}
    </div>
  );
}

export function TimeCourseChart({
  title,
  caption,
  times,
  series,
  timeUnit,
  unit,
  step = false,
  height = 300,
  width,
}: {
  title: string;
  caption?: string;
  times: readonly (number | null)[];
  series: Record<string, readonly (number | null)[]>;
  timeUnit: string;
  /** The unit of every series (a concentration, or "molecules"). */
  unit: string;
  step?: boolean;
  height?: number;
  /** A fixed width, where the container cannot be measured (tests). */
  width?: number;
}) {
  const names = useMemo(() => Object.keys(series), [series]);
  const rows = useMemo(() => timeCourseRows(times, series), [times, series]);
  const chart = (
    <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 22, left: 8 }} width={width} height={width ? height : undefined}>
      <CartesianGrid {...GRID} vertical={false} />
      <XAxis
        dataKey="t"
        type="number"
        domain={["dataMin", "dataMax"]}
        tickFormatter={tick}
        {...AXIS}
        label={{ value: `time (${timeUnit})`, position: "insideBottom", offset: -12 }}
      />
      <YAxis tickFormatter={tick} {...AXIS} width={56} label={{ value: unit, angle: -90, position: "insideLeft" }} />
      <Tooltip
        content={<ChartTooltip timeUnit={timeUnit} unit={unit} />}
        cursor={{ stroke: "var(--rule-strong)" }}
        isAnimationActive={false}
      />
      {names.map((n, i) => (
        <Line
          key={n}
          dataKey={n}
          name={n}
          type={step ? "stepAfter" : "linear"}
          stroke={seriesColor(i)}
          strokeDasharray={seriesDash(i)}
          strokeWidth={1.75}
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
      title={title}
      caption={caption}
      height={height}
      legend={names.map((n, i) => ({ label: n, index: i }))}
      table={
        <DataTable
          caption={`${title}: ${rows.length} time points`}
          captionHidden
          rows={rows}
          rowKey={(_, i) => String(i)}
          columns={[
            { key: "t", header: `time (${timeUnit})`, numeric: true, cell: (r) => (r.t === null ? "none" : formatNumber(r.t)) },
            ...names.map((n) => ({
              key: n,
              header: `${n} (${unit})`,
              numeric: true,
              cell: (r: Row) => (r[n] === null ? "none" : formatNumber(r[n] as number)),
            })),
          ]}
        />
      }
    >
      {width ? chart : <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer>}
    </ChartFrame>
  );
}
