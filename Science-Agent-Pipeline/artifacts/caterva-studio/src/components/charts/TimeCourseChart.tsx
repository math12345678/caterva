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
import { AXIS, GRID, niceTicks, seriesColor, seriesDash, SeriesMarker, SPARSE_POINTS, spreadLabels, tick, timeAxisTitle } from "./theme";

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
  const sparse = rows.length <= SPARSE_POINTS;
  const geometry = useMemo(() => {
    const finite = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);
    const ts = times.filter(finite);
    const all = names.flatMap((n) => series[n].filter(finite));
    const x = niceTicks(ts.length ? Math.min(...ts) : 0, ts.length ? Math.max(...ts) : 1, 6, false);
    const y = niceTicks(all.length ? Math.min(...all) : 0, all.length ? Math.max(...all) : 1, 5, true);
    const lastIndex = names.map((n) => {
      for (let i = series[n].length - 1; i >= 0; i--) if (finite(series[n][i])) return i;
      return -1;
    });
    const ends = names.map((n, k) => (lastIndex[k] >= 0 ? (series[n][lastIndex[k]] as number) : null));
    const plotHeight = height - 8 - 22;
    return { x, y, lastIndex, offsets: spreadLabels(ends, y.domain, plotHeight), ends, plotHeight };
  }, [times, series, names, height]);
  const labelWidth = Math.min(132, 12 + 7 * Math.max(0, ...names.map((n) => n.length)));
  const chart = (
    <LineChart
      data={rows}
      margin={{ top: 8, right: names.length > 1 ? labelWidth : 16, bottom: 22, left: 8 }}
      width={width}
      height={width ? height : undefined}
    >
      <CartesianGrid {...GRID} vertical={false} />
      <XAxis
        dataKey="t"
        type="number"
        domain={geometry.x.domain}
        ticks={geometry.x.ticks}
        tickFormatter={tick}
        {...AXIS}
        label={{ value: timeAxisTitle(timeUnit), position: "insideBottom", offset: -12 }}
      />
      <YAxis
        tickFormatter={tick}
        {...AXIS}
        width={56}
        domain={geometry.y.domain}
        ticks={geometry.y.ticks}
        label={{ value: unit, angle: -90, position: "insideLeft" }}
      />
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
          dot={sparse ? (p: { cx?: number; cy?: number; value?: unknown; key?: string }) => <SeriesMarker key={p.key} cx={p.cx} cy={p.cy} index={i} value={p.value} /> : false}
          activeDot={{ r: 3 }}
          connectNulls={false}
          isAnimationActive={false}
          label={
            names.length > 1
              ? (p: { x?: number; y?: number; index?: number }) =>
                  p.index === geometry.lastIndex[i] && typeof p.x === "number" && typeof p.y === "number" ? (
                    <text
                      key={`end-${n}`}
                      className="chart-end-label"
                      x={p.x + 8}
                      y={(geometry.offsets[i] === null ? p.y : 8 + (geometry.offsets[i] as number)) + 4}
                      fill={seriesColor(i)}
                    >
                      {n}
                    </text>
                  ) : (
                    <g key={`end-${n}-${p.index}`} />
                  )
              : undefined
          }
        />
      ))}
    </LineChart>
  );
  return (
    <ChartFrame
      title={title}
      caption={caption}
      height={height}
      summary={`${names.length} series (${names.join(", ")}) over ${rows.length} time points`}
      legend={names.map((n, i) => ({ label: n, index: i }))}
      table={
        <DataTable
          caption={`${title}: ${rows.length} time points`}
          captionHidden
          rows={rows}
          rowKey={(_, i) => String(i)}
          columns={[
            { key: "t", header: timeAxisTitle(timeUnit), numeric: true, cell: (r) => (r.t === null ? "none" : formatNumber(r.t)) },
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
